"""Canonical evidence serialization and an explicit Decimal execution context."""
import hashlib
import json
from dataclasses import asdict, is_dataclass
from datetime import date
from decimal import Context, Decimal, ROUND_HALF_EVEN

NUMERIC_CONTEXT = Context(prec=28, rounding=ROUND_HALF_EVEN)


def encode(value):
    if is_dataclass(value):
        return asdict(value)
    if isinstance(value, (Decimal, date)):
        return str(value)
    raise TypeError(type(value).__name__)


def canonical(value) -> str:
    return json.dumps(value, default=encode, sort_keys=True, indent=2, allow_nan=False) + "\n"


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()
