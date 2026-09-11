"""Explicit ordinary distributions and as-traded share splits; never infer events."""
import json
from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext

from .models import Bar, finite
from .serialization import NUMERIC_CONTEXT, canonical, digest


@dataclass(frozen=True)
class Dividend:
    ex_date: date
    pay_date: date
    amount: Decimal
    source: str

    def __post_init__(self):
        if type(self.ex_date) is not date or type(self.pay_date) is not date or self.pay_date < self.ex_date:
            raise ValueError("ordinary dividend requires ex_date <= pay_date; due bills unsupported")
        finite(self.amount, "dividend amount")
        if self.amount <= 0 or not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("dividend requires positive amount and source")

    @property
    def effective_date(self): return self.ex_date


@dataclass(frozen=True)
class Split:
    effective_date: date
    ratio: Decimal  # New shares per old share; prices must be as traded.
    source: str

    def __post_init__(self):
        finite(self.ratio, "split ratio")
        if type(self.effective_date) is not date or self.ratio <= 0 or self.ratio == 1 or not isinstance(self.source, str) or not self.source.strip():
            raise ValueError("split requires session date, positive non-unit ratio and source")


def action_records(actions):
    from dataclasses import asdict
    return [{"type": "dividend" if isinstance(a, Dividend) else "split", **asdict(a)} for a in actions]


def actions_digest(actions):
    return digest(canonical(action_records(actions)).encode())


def validate_actions(actions: tuple, bars: tuple[Bar, ...]):
    if type(actions) is not tuple or any(type(a) not in (Dividend, Split) for a in actions):
        raise ValueError("actions must be an immutable tuple of supported events")
    dates = [a.effective_date for a in actions]
    if dates != sorted(set(dates)):
        raise ValueError("actions must be sorted, one per date; simultaneous events unsupported")
    sessions = {b.date for b in bars}
    if any(day not in sessions for day in dates):
        raise ValueError("every action must fall on a supplied session")
    previous = {b.date: bars[i-1].close for i, b in enumerate(bars) if i}
    with localcontext(NUMERIC_CONTEXT):
        for a in actions:
            if isinstance(a, Dividend) and a.ex_date in previous and a.amount >= previous[a.ex_date] / 4:
                raise ValueError("large/special distributions require a due-bill model")


def parse_actions(raw: bytes, symbol: str) -> tuple:
    if not raw:
        return ()
    try:
        obj = json.loads(raw)
        if set(obj) != {"schema_version", "symbol", "price_basis", "events"} or obj["schema_version"] != 1 or obj["symbol"] != symbol:
            raise ValueError("action document schema or symbol mismatch")
        if obj["price_basis"] != "as_traded" or not isinstance(obj["events"], list):
            raise ValueError("action document requires as_traded prices and an event list")
        result = []
        for row in obj["events"]:
            if row["type"] == "dividend" and set(row) == {"type", "ex_date", "pay_date", "amount", "source"}:
                if not isinstance(row["amount"], str):
                    raise ValueError("amount must be a decimal string")
                result.append(Dividend(date.fromisoformat(row["ex_date"]), date.fromisoformat(row["pay_date"]), Decimal(row["amount"]), row["source"]))
            elif row["type"] == "split" and set(row) == {"type", "effective_date", "ratio", "source"}:
                if not isinstance(row["ratio"], str):
                    raise ValueError("ratio must be a decimal string")
                result.append(Split(date.fromisoformat(row["effective_date"]), Decimal(row["ratio"]), row["source"]))
            else:
                raise ValueError("unsupported or malformed corporate action")
        return tuple(result)
    except (KeyError, TypeError) as exc:
        raise ValueError("malformed action document") from exc
