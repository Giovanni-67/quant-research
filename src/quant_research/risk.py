"""Deterministic risk sizing and latched close-based circuit breakers."""
from dataclasses import dataclass, replace
from decimal import Decimal, localcontext
from .models import Decision, finite
from .serialization import NUMERIC_CONTEXT


def wilder_atr(bars, window=14):
    if type(window) is not int or window < 1:
        raise ValueError("ATR window must be a positive integer")
    if len(bars) < window: return None
    with localcontext(NUMERIC_CONTEXT):
        ranges = [bars[0].high-bars[0].low]
        ranges.extend(max(b.high-b.low,abs(b.high-a.close),abs(b.low-a.close)) for a,b in zip(bars,bars[1:]))
        value = sum(ranges[:window]) / window
        for item in ranges[window:]: value = (value*(window-1)+item)/window
        return value


@dataclass(frozen=True)
class RiskRules:
    max_drawdown: Decimal = Decimal('.10')
    max_daily_loss: Decimal = Decimal('.03')
    max_exposure: Decimal = Decimal('.25')
    risk_per_trade: Decimal = Decimal('.01')
    atr_multiple: Decimal = Decimal('2')
    atr_window: int = 14

    def __post_init__(self):
        for name in ('max_drawdown','max_daily_loss','max_exposure','risk_per_trade'):
            finite(getattr(self,name),name)
            if not 0 < getattr(self,name) <= 1: raise ValueError(f'{name} must be in (0,1]')
        finite(self.atr_multiple,'atr_multiple')
        if self.atr_multiple <= 0 or type(self.atr_window) is not int or self.atr_window < 1:
            raise ValueError('ATR settings must be positive')


class RiskManaged:
    def __init__(self, strategy, initial_cash, rules=RiskRules()):
        self.inner, self.rules = strategy, rules
        self.peak = self.previous = initial_cash
        self.halted = False
        self.config = {'strategy':type(strategy).__name__,'parameters':getattr(strategy,'config',None),
                       'risk':rules,'initial_cash':initial_cash}

    def on_split(self, ratio): self.inner.on_split(ratio)

    def decide(self, history, portfolio):
        with localcontext(NUMERIC_CONTEXT):
            equity = portfolio.cash + portfolio.quantity*history[-1].close + portfolio.receivable
            self.peak = max(self.peak,equity)
            if equity/self.peak-1 <= -self.rules.max_drawdown or equity/self.previous-1 <= -self.rules.max_daily_loss:
                self.halted = True
            self.previous = equity
            if self.halted:
                return Decision('SELL','RISK_HALT: latched close-based loss circuit breaker') if portfolio.quantity else None
            if portfolio.quantity and portfolio.quantity*history[-1].close/equity > self.rules.max_exposure:
                return Decision('SELL','risk exposure ceiling breached at close')
            atr = wilder_atr(history,self.rules.atr_window) if not portfolio.quantity else None
            # Do not consume a one-shot strategy's entry while sizing is unavailable.
            if not portfolio.quantity and (atr is None or atr <= 0): return None
            decision = self.inner.decide(history,portfolio)
            if decision and decision.action == 'BUY':
                if atr is None: atr = wilder_atr(history,self.rules.atr_window)
                if atr is None or atr <= 0: return None
                cap=equity*self.rules.risk_per_trade/(atr*self.rules.atr_multiple)
                if decision.max_quantity is not None: cap=min(cap,decision.max_quantity)
                return replace(decision,max_quantity=cap)
            return decision
