"""Single-asset, cash-funded simulation with close decisions / next-open fills."""
from decimal import Decimal, ROUND_FLOOR, ROUND_HALF_UP, localcontext
from datetime import date
from dataclasses import replace
from typing import Protocol

from .data import validate_bars
from .models import (
    Bar, Config, Decision, EquityPoint, Fill, PortfolioView, Rejection,
    Result, Signal, ZERO, ActionEntry,
)
from .actions import Dividend, Split, validate_actions, actions_digest
from .serialization import NUMERIC_CONTEXT, canonical, digest
from .source import checked_source

CENT = Decimal("0.01")
BPS = Decimal("10000")


class Strategy(Protocol):
    def decide(self, history: tuple[Bar, ...], portfolio: PortfolioView) -> Decision | None: ...


def cents(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _execute(signal, bar, cash, quantity, cfg):
    action = signal.decision.action
    if (action == "BUY" and quantity != ZERO) or (action == "SELL" and quantity == ZERO):
        return None, "BUY requires flat holdings; SELL requires an open position"
    direction = Decimal("1") if action == "BUY" else Decimal("-1")
    price = bar.open * (1 + direction * cfg.slippage_bps / BPS)
    if action == "BUY":
        # No borrowing: allocation includes fees and adverse slippage.
        budget = min(cash, cash * cfg.max_position_weight)
        units = (budget / (price * (1 + cfg.fee_bps / BPS)) / cfg.lot_size).to_integral_value(rounding=ROUND_FLOOR)
        quantity = units * cfg.lot_size
        if signal.decision.max_quantity is not None:
            cap = (signal.decision.max_quantity / cfg.lot_size).to_integral_value(rounding=ROUND_FLOOR) * cfg.lot_size
            quantity = min(quantity, cap)
        while quantity > ZERO:
            notional = cents(quantity * price)
            fee = cents(notional * cfg.fee_bps / BPS)
            if notional + fee <= budget:
                break
            quantity -= cfg.lot_size
        if quantity <= ZERO or notional <= ZERO:
            return None, "allocation cannot fund one lot including costs"
        new_cash, new_quantity = cash - notional - fee, quantity
    else:
        notional = cents(quantity * price)
        fee = cents(notional * cfg.fee_bps / BPS)
        new_cash, new_quantity = cash + notional - fee, ZERO
    if new_cash < ZERO or new_quantity < ZERO:
        raise RuntimeError("cash/quantity invariant violated")
    return Fill(signal.date, bar.date, action, quantity, bar.open, price,
                notional, fee, new_cash, new_quantity, signal.decision.reason), None


def run(bars: tuple[Bar, ...], strategy: Strategy, config: Config = Config(), *,
        actions: tuple = (), decision_start: date | None = None) -> Result:
    """Pass a fresh strategy instance per run. Open positions remain marked, not liquidated."""
    validate_bars(bars)
    _, source_sha = checked_source()
    with localcontext(NUMERIC_CONTEXT):
        validate_actions(actions, bars)
        if decision_start is not None and decision_start not in {b.date for b in bars}:
            raise ValueError("decision_start must be a supplied session")
        if any(isinstance(a, Split) for a in actions) and not callable(getattr(strategy, "on_split", None)):
            raise ValueError("strategy must explicitly support on_split for split data")
        cash, quantity = config.initial_cash, ZERO
        receivable = ZERO
        owed, ledger, history = [], [], ()
        by_date = {a.effective_date: a for a in actions}
        spec = {"implementation": f"{type(strategy).__module__}.{type(strategy).__qualname__}",
                "parameters": getattr(strategy, "config", None)}
        spec_json = canonical(spec)  # Freeze before strategy state can mutate.
        entry_price, entry_index, pending = None, None, None
        fills, signals, rejections, equity = [], [], [], []
        for i, bar in enumerate(bars):
            action = by_date.get(bar.date)
            if isinstance(action, Split):
                quantity *= action.ratio
                if quantity % config.lot_size:
                    raise ValueError("split creates fractional lots; cash-in-lieu is unsupported")
                if entry_price is not None:
                    entry_price /= action.ratio
                history = tuple(replace(b, open=b.open/action.ratio, high=b.high/action.ratio,
                                        low=b.low/action.ratio, close=b.close/action.ratio,
                                        volume=b.volume*action.ratio) for b in history)
                strategy.on_split(action.ratio)
                if pending is not None and pending.decision.max_quantity is not None:
                    pending = replace(pending, decision=replace(pending.decision,
                        max_quantity=pending.decision.max_quantity*action.ratio))
                ledger.append(ActionEntry(bar.date, bar.date, "split", quantity, action.ratio, cash, receivable))
            elif isinstance(action, Dividend) and quantity:
                amount = cents(quantity * action.amount)
                receivable += amount
                owed.append((action, amount, quantity))
                ledger.append(ActionEntry(bar.date, bar.date, "dividend_entitlement", quantity, amount, cash, receivable))
            # Conservatively available at first supplied open AFTER the payable date.
            for event, amount, entitled_quantity in tuple(owed):
                if bar.date > event.pay_date:
                    cash += amount
                    receivable -= amount
                    owed.remove((event, amount, entitled_quantity))
                    ledger.append(ActionEntry(bar.date, event.ex_date, "dividend_payment", entitled_quantity, amount, cash, receivable))
            if pending is not None:
                fill, reason = _execute(pending, bar, cash, quantity, config)
                if fill is None:
                    rejections.append(Rejection(pending.date, bar.date, pending.decision.action, reason))
                else:
                    fills.append(fill)
                    cash, quantity = fill.cash_after, fill.quantity_after
                    entry_price = fill.price if fill.action == "BUY" else None
                    entry_index = i if fill.action == "BUY" else None
                pending = None
            history += (bar,)
            if decision_start is not None and bar.date < decision_start:
                continue
            equity.append(EquityPoint(bar.date, cash, quantity, bar.close, cash + quantity * bar.close + receivable, receivable))
            view = PortfolioView(cash, quantity, entry_price, 0 if entry_index is None else i - entry_index + 1, receivable)
            decision = strategy.decide(history, view)
            if decision is not None:
                if not isinstance(decision, Decision):
                    raise ValueError("strategy must return Decision or None")
                pending = Signal(bar.date, decision)
                signals.append(pending)
        return Result(config, tuple(fills), tuple(signals), tuple(rejections), tuple(equity), pending,
                      digest(canonical(bars).encode()), spec_json, source_sha,
                      actions_digest(actions), tuple(ledger), decision_start, bool(getattr(strategy,'halted',False)))
