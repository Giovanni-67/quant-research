from dataclasses import dataclass
from decimal import Decimal, localcontext

from .models import Bar, Decision, PortfolioView, ZERO, finite
from .serialization import NUMERIC_CONTEXT


def sma(values: tuple[Decimal, ...], window: int) -> Decimal | None:
    if type(window) is not int or window <= 0:
        raise ValueError("window must be a positive integer")
    with localcontext(NUMERIC_CONTEXT):
        return None if len(values) < window else sum(values[-window:]) / window


def bollinger(values: tuple[Decimal, ...], window: int = 20, width: Decimal = Decimal("2")):
    """Population standard deviation (ddof=0); returns lower, mean, upper."""
    finite(width, "width")
    if width < ZERO:
        raise ValueError("width must be nonnegative")
    with localcontext(NUMERIC_CONTEXT):
        mean = sma(values, window)
        if mean is None:
            return None
        deviation = (sum((v - mean) ** 2 for v in values[-window:]) / window).sqrt()
        return mean - width * deviation, mean, mean + width * deviation


@dataclass(frozen=True)
class BreakoutConfig:
    lookback: int = 20
    breakout_buffer: Decimal = Decimal("0.005")
    retest_tolerance: Decimal = Decimal("0.01")
    retest_bars: int = 3
    max_holding_bars: int = 5
    stop_fraction: Decimal = Decimal("0.05")
    profit_fraction: Decimal = Decimal("0.10")

    def __post_init__(self):
        for name in ("lookback", "retest_bars", "max_holding_bars"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        for name in ("breakout_buffer", "retest_tolerance", "stop_fraction", "profit_fraction"):
            value = getattr(self, name)
            finite(value, name)
            if not ZERO <= value < 1:
                raise ValueError(f"{name} must be in [0, 1)")
        if self.stop_fraction == ZERO or self.profit_fraction == ZERO:
            raise ValueError("stop and profit fractions must be positive")


class BreakoutRetest:
    def __init__(self, config: BreakoutConfig = BreakoutConfig()):
        self.config = config
        self.level = None
        self.breakout_index = None

    def on_split(self, ratio):
        if self.level is not None:
            self.level /= ratio

    def decide(self, history: tuple[Bar, ...], portfolio: PortfolioView):
        cfg, bar, index = self.config, history[-1], len(history) - 1
        if portfolio.quantity > ZERO:
            self.level = self.breakout_index = None
            if bar.close <= portfolio.entry_price * (1 - cfg.stop_fraction):
                return Decision("SELL", "close-based stop; exit at next available session open")
            if bar.close >= portfolio.entry_price * (1 + cfg.profit_fraction):
                return Decision("SELL", "close-based profit exit")
            if portfolio.holding_bars >= cfg.max_holding_bars:
                return Decision("SELL", "maximum holding bars reached")
            return None
        if self.level is not None:
            level, age = self.level, index - self.breakout_index
            if age > cfg.retest_bars or bar.close < level * (1 - cfg.retest_tolerance):
                self.level = self.breakout_index = None
                return None
            if age >= 1 and level * (1 - cfg.retest_tolerance) <= bar.low <= level * (1 + cfg.retest_tolerance) and bar.close >= level:
                self.level = self.breakout_index = None
                return Decision("BUY", "breakout retest confirmed at close", level)
            return None
        if len(history) <= cfg.lookback:
            return None
        resistance = max(b.high for b in history[-cfg.lookback - 1:-1])
        if bar.close > resistance * (1 + cfg.breakout_buffer):
            self.level, self.breakout_index = resistance, index
        return None


class BuyAndHold:
    """Submit once on the first close; use the same next-open execution convention."""
    def __init__(self): self.submitted = False

    def on_split(self, ratio): pass

    def decide(self, history, portfolio):
        if not self.submitted:
            self.submitted = True
            return Decision("BUY", "buy-and-hold baseline")
        return None


class CashOnly:
    def on_split(self, ratio): pass

    def decide(self, history, portfolio):
        return None


@dataclass(frozen=True)
class TechnicalConfig:
    family: str = "trend"
    lookback: int = 20
    fast_window: int = 5
    width: Decimal = Decimal("2")
    max_holding_bars: int = 5
    stop_fraction: Decimal = Decimal(".05")
    profit_fraction: Decimal = Decimal(".10")

    def __post_init__(self):
        if self.family not in ("trend", "bollinger"):
            raise ValueError("unknown technical strategy family")
        BreakoutConfig(lookback=self.lookback, max_holding_bars=self.max_holding_bars,
                       stop_fraction=self.stop_fraction, profit_fraction=self.profit_fraction)
        if type(self.fast_window) is not int or not 0 < self.fast_window < self.lookback:
            raise ValueError("fast_window must be positive and below lookback")
        finite(self.width, "width")
        if self.width <= 0:
            raise ValueError("Bollinger width must be positive")


class TechnicalSwing:
    """Two explicit hypotheses, not an adaptive 'whatever works' selector."""
    def __init__(self, config: TechnicalConfig = TechnicalConfig()):
        self.config = config

    def on_split(self, ratio): pass  # No stored price levels; engine rebases history.

    def decide(self, history, portfolio):
        cfg, close = self.config, history[-1].close
        values = tuple(b.close for b in history)
        if portfolio.quantity:
            if close <= portfolio.entry_price * (1-cfg.stop_fraction):
                return Decision("SELL", "close-based stop; next-open exit")
            if close >= portfolio.entry_price * (1+cfg.profit_fraction):
                return Decision("SELL", "close-based profit exit")
            if portfolio.holding_bars >= cfg.max_holding_bars:
                return Decision("SELL", "maximum holding bars reached")
            mean = sma(values, cfg.lookback)
            if mean is not None and ((cfg.family == "bollinger" and close >= mean) or
                                     (cfg.family == "trend" and sma(values, cfg.fast_window) <= mean)):
                return Decision("SELL", f"{cfg.family} exit confirmed at close")
            return None
        if len(values) < cfg.lookback + 1:
            return None
        if cfg.family == "trend":
            fast, slow = sma(values, cfg.fast_window), sma(values, cfg.lookback)
            prev_fast, prev_slow = sma(values[:-1], cfg.fast_window), sma(values[:-1], cfg.lookback)
            if prev_fast <= prev_slow and fast > slow:
                return Decision("BUY", "fast SMA crossed above slow SMA at close")
        else:
            previous_lower = bollinger(values[:-1], cfg.lookback, cfg.width)[0]
            lower = bollinger(values, cfg.lookback, cfg.width)[0]
            if values[-2] < previous_lower and close >= lower:
                return Decision("BUY", "close re-entered lower Bollinger band")
        return None


def research_strategies(breakout: BreakoutConfig = BreakoutConfig()):
    """Fresh state each call; all candidates are recorded, with no winner selection."""
    return {
        "breakout_retest": BreakoutRetest(breakout),
        "trend_swing": TechnicalSwing(TechnicalConfig(family="trend")),
        "bollinger_swing": TechnicalSwing(TechnicalConfig(family="bollinger")),
        "buy_and_hold_same_allocation": BuyAndHold(),
        "cash": CashOnly(),
    }
