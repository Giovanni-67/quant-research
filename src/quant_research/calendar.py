"""Bounded, versioned NYSE-family core-session calendar. Fail outside coverage."""
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from importlib.resources import files
from zoneinfo import ZoneInfo

from .serialization import digest


@dataclass(frozen=True)
class Session:
    date: date
    open_utc: datetime
    close_utc: datetime


def exchange_zone() -> ZoneInfo:
    # Bypass machine-global TZPATH so the pinned package controls the rules.
    with files("tzdata").joinpath("zoneinfo/America/New_York").open("rb") as handle:
        return ZoneInfo.from_file(handle, key="America/New_York")


def schedule(start: date, end: date) -> tuple[Session, ...]:
    """Inclusive start, exclusive end. Daily core sessions, not intraday halts."""
    raw = files("quant_research").joinpath("resources/nyse_calendar.json").read_bytes()
    rules = json.loads(raw)
    if end <= start:
        raise ValueError("end must be after start")
    if start.year not in rules["supported_years"] or (end - timedelta(days=1)).year not in rules["supported_years"]:
        raise ValueError("calendar supports 2025-2026 only; unsupported dates are not guessed")
    zone = exchange_zone()
    sessions = []
    day = start
    while day < end:
        if day.weekday() < 5 and day.isoformat() not in rules["holidays"]:
            close = rules["early_close"] if day.isoformat() in rules["early_closes"] else rules["regular_close"]
            sessions.append(Session(day,
                datetime.combine(day, time.fromisoformat(rules["regular_open"]), zone).astimezone(timezone.utc),
                datetime.combine(day, time.fromisoformat(close), zone).astimezone(timezone.utc)))
        day += timedelta(days=1)
    return tuple(sessions)


def calendar_identity() -> dict:
    raw = files("quant_research").joinpath("resources/nyse_calendar.json").read_bytes()
    rules = json.loads(raw)
    return {"version": rules["version"], "sha256": digest(raw), "sources": rules["sources"]}


def latest_completed_session(now: datetime) -> Session:
    if now.tzinfo is None: raise ValueError('clock must include timezone')
    rules=json.loads(files('quant_research').joinpath('resources/nyse_calendar.json').read_bytes())
    today=now.astimezone(timezone.utc).date()
    if today.year not in rules['supported_years']:raise ValueError('clock is outside calendar coverage')
    start=max(today-timedelta(days=14),date(min(rules['supported_years']),1,1))
    completed=[s for s in schedule(start,today+timedelta(days=1)) if s.close_utc<now]
    if not completed:raise ValueError('no completed session in supported calendar window')
    return completed[-1]


def check_sessions(bars, start: date, end: date) -> dict:
    expected = {s.date for s in schedule(start, end)}
    actual = {b.date for b in bars}
    missing, unexpected = sorted(expected - actual), sorted(actual - expected)
    if missing or unexpected:
        raise ValueError(f"session mismatch: missing={[str(d) for d in missing]}, unexpected={[str(d) for d in unexpected]}")
    return {"status": "passed", "session_count": len(expected), "start_inclusive": start.isoformat(),
            "end_exclusive": end.isoformat(), "calendar": calendar_identity()}
