import csv
import io
import json
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .models import Bar
from .serialization import canonical, digest
from .actions import parse_actions, validate_actions, actions_digest


def validate_bars(bars: tuple[Bar, ...]) -> None:
    if not bars:
        raise ValueError("at least one bar is required")
    if any(bar.volume == 0 for bar in bars):
        raise ValueError("zero-volume bars require data review; simulation is not allowed")
    for previous, current in zip(bars, bars[1:]):
        if current.date <= previous.date:
            raise ValueError("bars must be strictly increasing with no duplicate sessions")


def read_csv(path: Path) -> tuple[Bar, ...]:
    """Import explicit OHLCV session dates; never sort, repair, or forward-fill."""
    return parse_csv(path.read_bytes())


def parse_csv(raw: bytes) -> tuple[Bar, ...]:
    with io.StringIO(raw.decode("utf-8-sig"), newline="") as handle:
        reader = csv.DictReader(handle)
        required = ["date", "open", "high", "low", "close", "volume"]
        if reader.fieldnames != required:
            raise ValueError(f"CSV columns must be exactly {','.join(required)}")
        rows = []
        for line, row in enumerate(reader, 2):
            try:
                if None in row or any(v is None or not v.strip() for v in row.values()):
                    raise ValueError("missing or extra field")
                rows.append(Bar(date.fromisoformat(row["date"]), *(
                    Decimal(row[name]) for name in required[1:]
                )))
            except (ValueError, InvalidOperation) as exc:
                raise ValueError(f"invalid CSV row {line}: {exc}") from exc
    bars = tuple(rows)
    validate_bars(bars)
    return bars


@dataclass(frozen=True)
class Dataset:
    """One immutable read. Bars and hashes always derive from these exact bytes."""
    raw: bytes
    symbol: str
    kind: str
    provenance_json: str = "{}"
    actions_raw: bytes = b""
    bars: tuple[Bar, ...] = field(init=False)
    actions: tuple = field(init=False)

    def __post_init__(self):
        if type(self.raw) is not bytes or not self.symbol or not self.kind:
            raise ValueError("dataset needs immutable bytes, symbol and classification")
        if not isinstance(json.loads(self.provenance_json), dict):
            raise ValueError("provenance must be a JSON object")
        object.__setattr__(self, "bars", parse_csv(self.raw))
        if type(self.actions_raw) is not bytes:
            raise ValueError("action document must be immutable bytes")
        actions = parse_actions(self.actions_raw, self.symbol)
        validate_actions(actions, self.bars)
        object.__setattr__(self, "actions", actions)

    @classmethod
    def from_path(cls, path: Path, symbol: str, kind: str, actions_path: Path | None = None):
        return cls(path.read_bytes(), symbol, kind, actions_raw=actions_path.read_bytes() if actions_path else b"")

    @property
    def actions_sha256(self):
        return actions_digest(self.actions)

    @property
    def sha256(self):
        return digest(self.raw)

    @property
    def bars_sha256(self):
        return digest(canonical(self.bars).encode())
