from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Literal
from .serialization import NUMERIC_CONTEXT

ZERO = Decimal("0")
ONE = Decimal("1")


def finite(value: Decimal, name: str) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")


@dataclass(frozen=True)
class Bar:
    date: date
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self):
        if type(self.date) is not date:
            raise ValueError("bar date must be a session date")
        for field in ("open", "high", "low", "close", "volume"):
            finite(getattr(self, field), field)
        if min(self.open, self.high, self.low, self.close) <= ZERO:
            raise ValueError("OHLC prices must be positive")
        if self.volume < ZERO:
            raise ValueError("volume must be nonnegative")
        if not self.low <= min(self.open, self.close) <= max(self.open, self.close) <= self.high:
            raise ValueError("inconsistent OHLC range")


@dataclass(frozen=True)
class Config:
    initial_cash: Decimal = Decimal("1000")
    max_position_weight: Decimal = Decimal("0.20")
    fee_bps: Decimal = Decimal("5")
    slippage_bps: Decimal = Decimal("5")
    lot_size: Decimal = Decimal("1")

    def __post_init__(self):
        for name in self.__dataclass_fields__:
            finite(getattr(self, name), name)
        with localcontext(NUMERIC_CONTEXT):
            if self.initial_cash <= ZERO or self.initial_cash > Decimal("1000000000000") or self.initial_cash != self.initial_cash.quantize(Decimal("0.01")):
                raise ValueError("initial_cash must be positive, <= 1 trillion and denominated in cents")
        if not ZERO < self.max_position_weight <= ONE:
            raise ValueError("max_position_weight must be in (0, 1]")
        if not ZERO <= self.fee_bps < Decimal("10000"):
            raise ValueError("fee_bps must be in [0, 10000)")
        if not ZERO <= self.slippage_bps < Decimal("10000"):
            raise ValueError("slippage_bps must be in [0, 10000)")
        if self.lot_size <= ZERO:
            raise ValueError("lot_size must be positive")


@dataclass(frozen=True)
class Decision:
    action: Literal["BUY", "SELL"]
    reason: str
    level: Decimal | None = None
    max_quantity: Decimal | None = None

    def __post_init__(self):
        if self.action not in ("BUY", "SELL") or not self.reason:
            raise ValueError("decision needs BUY/SELL and a reason")
        if self.level is not None:
            finite(self.level, "level")
        if self.max_quantity is not None:
            finite(self.max_quantity, "max_quantity")
            if self.max_quantity < ZERO:
                raise ValueError("max_quantity must be nonnegative")


@dataclass(frozen=True)
class PortfolioView:
    cash: Decimal
    quantity: Decimal
    entry_price: Decimal | None
    holding_bars: int
    receivable: Decimal = ZERO


@dataclass(frozen=True)
class Signal:
    date: date
    decision: Decision


@dataclass(frozen=True)
class Fill:
    signal_date: date
    date: date
    action: str
    quantity: Decimal
    reference_price: Decimal
    price: Decimal
    notional: Decimal
    fee: Decimal
    cash_after: Decimal
    quantity_after: Decimal
    reason: str


@dataclass(frozen=True)
class Rejection:
    signal_date: date
    date: date
    action: str
    reason: str


@dataclass(frozen=True)
class EquityPoint:
    date: date
    cash: Decimal
    quantity: Decimal
    close: Decimal
    equity: Decimal
    receivable: Decimal = ZERO


@dataclass(frozen=True)
class ActionEntry:
    date: date
    event_date: date
    kind: str
    quantity: Decimal
    amount: Decimal
    cash_after: Decimal
    receivable_after: Decimal


@dataclass(frozen=True)
class Result:
    config: Config
    fills: tuple[Fill, ...]
    signals: tuple[Signal, ...]
    rejections: tuple[Rejection, ...]
    equity: tuple[EquityPoint, ...]
    pending: Signal | None
    bars_sha256: str
    strategy_spec_json: str
    source_sha256: str
    actions_sha256: str
    action_ledger: tuple[ActionEntry, ...]
    decision_start: date | None
    risk_halted: bool = False
