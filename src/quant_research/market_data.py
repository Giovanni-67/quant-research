"""Experimental Yahoo chart adapter with frozen payloads and strict admission checks.

The endpoint is public but unofficial: no reliability/redistribution guarantee.
No adjusted-close scaling is applied. Ordinary dividends need an explicit matching
payment-date supplement. Vendor split windows remain rejected. Engineering-only.
"""
import csv
import io
import json
import re
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from importlib.metadata import version
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .calendar import check_sessions, schedule, exchange_zone
from .data import Dataset
from .actions import Dividend, parse_actions
from .serialization import NUMERIC_CONTEXT, canonical, digest
from .storage import publish, verify

POLICY = "reject_reported_corporate_actions_v1"
SNAPSHOT_FILES = {"raw_response.json", "bars.csv", "metadata.json"}
MAX_PAYLOAD = 20_000_000


def request_url(symbol: str, start: date, end: date) -> str:
    if not re.fullmatch(r"[A-Z][A-Z0-9.-]{0,9}", symbol):
        raise ValueError("unsupported ticker syntax")
    schedule(start, end)  # Validate bounded coverage before any network request.
    params = {"period1": int(datetime.combine(start, datetime.min.time(), timezone.utc).timestamp()),
              "period2": int(datetime.combine(end, datetime.min.time(), timezone.utc).timestamp()),
              "interval": "1d", "events": "div,splits,capitalGains", "includeAdjustedClose": "true"}
    return f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}?{urlencode(params)}"


def _parse(raw: bytes, symbol: str, start: date, end: date, actions_raw: bytes = b"") -> tuple[bytes, dict]:
    try:
        with localcontext(NUMERIC_CONTEXT):
            payload = json.loads(raw, parse_float=Decimal)
            chart = payload["chart"]
            if chart.get("error") or not chart.get("result") or len(chart["result"]) != 1:
                raise ValueError("provider returned an error or ambiguous result")
            record = chart["result"][0]
            meta = record["meta"]
            if (meta["symbol"] != symbol or meta["currency"] != "USD" or meta["instrumentType"] not in ("ETF", "EQUITY")
                    or meta["exchangeTimezoneName"] != "America/New_York" or meta["exchangeName"] not in ("PCX", "NYQ")):
                raise ValueError("adapter currently supports USD stocks/ETFs on NYSE/Arca only")
            if meta.get("dataGranularity") != "1d":
                raise ValueError("provider response is not daily data")
            events = record.get("events", {})
            if not isinstance(events, dict):
                raise ValueError("invalid events structure")
            actions = parse_actions(actions_raw, symbol)
            if any(value for key, value in events.items() if key != "dividends") or any(not isinstance(a, Dividend) for a in actions):
                raise ValueError("unsupported corporate actions: vendor split scaling/capital gains/unknown events")
            dividends = events.get("dividends", {})
            if not isinstance(dividends, dict):
                raise ValueError("invalid corporate actions structure")
            if dividends and not actions_raw:
                raise ValueError("corporate actions require an explicit dividend payment-date supplement")
            reported = []
            for event in dividends.values():
                if type(event["date"]) is not int or isinstance(event["amount"], bool):
                    raise ValueError("invalid corporate actions date/amount")
                reported.append((datetime.fromtimestamp(event["date"], exchange_zone()).date(), Decimal(event["amount"])))
            reported.sort()
            if len(reported) != len(actions) or any(
                day != a.ex_date or not (amount == a.amount or (
                    amount == amount.quantize(Decimal(".001")) and
                    amount == a.amount.quantize(Decimal(".001"), rounding=ROUND_HALF_UP)))
                for (day, amount), a in zip(reported, actions)
            ):
                raise ValueError("corporate actions supplement disagrees with vendor ex-dates/amounts (exact or 0.001 rounding)")
            timestamps = record["timestamp"]
            quote = record["indicators"]["quote"][0]
            if not timestamps or any(len(quote[k]) != len(timestamps) for k in ("open", "high", "low", "close", "volume")):
                raise ValueError("empty or misaligned price arrays")
            output = io.StringIO(newline="")
            writer = csv.writer(output, lineterminator="\n")
            writer.writerow(["date", "open", "high", "low", "close", "volume"])
            zone = exchange_zone()
            for i, stamp in enumerate(timestamps):
                if type(stamp) is not int:
                    raise ValueError("invalid bar timestamp")
                day = datetime.fromtimestamp(stamp, zone).date()
                if not start <= day < end:
                    raise ValueError("provider returned an out-of-window bar")
                values = []
                for field in ("open", "high", "low", "close", "volume"):
                    value = quote[field][i]
                    if value is None or isinstance(value, bool) or not isinstance(value, (Decimal, int)):
                        raise ValueError(f"null or nonnumeric {field} for {day}")
                    value = Decimal(value)
                    if not value.is_finite():
                        raise ValueError(f"nonfinite {field}")
                    if field == "volume" and value != value.to_integral_value():
                        raise ValueError("fractional reported share volume")
                    # Preserve provider decimals; do not silently round/repair OHLC.
                    values.append(str(value))
                writer.writerow([day.isoformat(), *values])
            normalized = output.getvalue().encode()
            dataset = Dataset(normalized, symbol, "vendor_checked_engineering_only", actions_raw=actions_raw)
            quality = check_sessions(dataset.bars, start, end)
            quality.update({"corporate_action_policy": "explicit_ordinary_dividends_v1" if actions_raw else POLICY, "reported_action_count": len(actions),
                            "ohlcv": "passed", "provider_metadata": {
                                k: meta[k] for k in ("symbol", "currency", "instrumentType", "exchangeName", "exchangeTimezoneName", "dataGranularity")}})
            if actions_raw:
                quality["dividend_reconciliation"] = [{"ex_date": str(a.ex_date), "vendor_amount": str(amount),
                    "ledger_amount": str(a.amount), "pay_date": str(a.pay_date), "source": a.source,
                    "match": "exact" if amount == a.amount else "vendor_rounded_to_0.001"}
                    for (_, amount), a in zip(reported, actions)]
            return normalized, quality
    except (KeyError, IndexError, TypeError, json.JSONDecodeError, OverflowError) as exc:
        raise ValueError(f"malformed provider response: {exc}") from exc


def create_snapshot(root: Path, raw: bytes, symbol: str, start: date, end: date,
                    retrieved_at: str, url: str, actions_raw: bytes = b"") -> Path:
    expected_url = request_url(symbol, start, end)
    if url != expected_url:
        raise ValueError("source URL does not match the required request contract")
    fetched = datetime.fromisoformat(retrieved_at)
    if fetched.tzinfo is None:
        raise ValueError("retrieval timestamp must include a timezone")
    sessions = schedule(start, end)
    if not sessions or sessions[-1].close_utc >= fetched:
        raise ValueError("requested data includes a session not completed at retrieval")
    bars, quality = _parse(raw, symbol, start, end, actions_raw)
    metadata = {
        "schema_version": 1, "adapter": "yahoo_chart_experimental_v1", "symbol": symbol,
        "start": str(start), "end": str(end), "source_url": url, "retrieved_at": retrieved_at,
        "raw_sha256": digest(raw), "bars_sha256": digest(bars), "quality": quality,
        "tzdata_version": version("tzdata"),
        "price_policy": "vendor quote OHLC retained; adjusted-close not applied; historical revisions/split scaling not independently verified",
        "limitations": ["single vendor; absence of reported actions is not independent proof",
                        "no point-in-time archive; vendor may retrospectively revise prices",
                        "no redistribution rights established; local personal research copy",
                        "no profitability validation or historical universe selection"],
    }
    if actions_raw:
        metadata["actions_raw_sha256"] = digest(actions_raw)
        metadata["limitations"].append("supplement payment dates are user-supplied with source references; parser does not authenticate those references")
    identity = digest(canonical(metadata).encode())[:20]
    artifacts = {"raw_response.json": raw, "bars.csv": bars, "metadata.json": canonical(metadata).encode()}
    if actions_raw:
        artifacts["actions.json"] = actions_raw
    return publish(root, identity, artifacts)


def load_snapshot(path: Path) -> Dataset:
    metadata = json.loads((path / "metadata.json").read_text(encoding="utf-8"))
    has_actions = "actions_raw_sha256" in metadata
    verify(path, SNAPSHOT_FILES | ({"actions.json"} if has_actions else set()))
    raw = (path / "raw_response.json").read_bytes()
    actions_raw = (path / "actions.json").read_bytes() if has_actions else b""
    if has_actions and digest(actions_raw) != metadata["actions_raw_sha256"]:
        raise ValueError("action supplement integrity mismatch")
    start, end = date.fromisoformat(metadata["start"]), date.fromisoformat(metadata["end"])
    if metadata["source_url"] != request_url(metadata["symbol"], start, end):
        raise ValueError("snapshot request contract mismatch")
    normalized, quality = _parse(raw, metadata["symbol"], start, end, actions_raw)
    if (digest(raw) != metadata["raw_sha256"] or digest(normalized) != metadata["bars_sha256"]
            or normalized != (path / "bars.csv").read_bytes() or quality != metadata["quality"]):
        raise ValueError("snapshot no longer matches its raw data and validation rules")
    return Dataset(normalized, metadata["symbol"], "vendor_checked_engineering_only", canonical(metadata), actions_raw)


def fetch(root: Path, symbol: str, start: date, end: date, actions_raw: bytes = b"") -> Path:
    url = request_url(symbol, start, end)
    now = datetime.now(timezone.utc)
    sessions = schedule(start, end)
    if not sessions or sessions[-1].close_utc >= now:
        raise ValueError("fetch only completed historical sessions")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 quant-research personal-use"})
    with urlopen(request, timeout=30) as response:
        raw = response.read(MAX_PAYLOAD + 1)
    if len(raw) > MAX_PAYLOAD:
        raise ValueError("provider response exceeds size limit")
    return create_snapshot(root, raw, symbol, start, end, datetime.now(timezone.utc).isoformat(), url, actions_raw)
