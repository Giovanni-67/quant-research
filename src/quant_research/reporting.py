"""Portable evidence bundles and a self-contained HTML/SVG report."""
import csv
import html
import io
import json
import platform
from dataclasses import asdict
from decimal import Decimal, localcontext
from pathlib import Path

from .models import Result
from .data import Dataset
from .serialization import NUMERIC_CONTEXT, canonical, digest
from .storage import publish
from .source import checked_source


def metrics(result: Result) -> dict:
    with localcontext(NUMERIC_CONTEXT):
        initial = result.config.initial_cash
        peak, max_dd = initial, Decimal("0")
        for point in result.equity:
            peak = max(peak, point.equity)
            max_dd = min(max_dd, point.equity / peak - 1)
        final = result.equity[-1]
        return {
            "initial_equity": initial,
            "final_equity": final.equity,
            "total_return": final.equity / initial - 1,
            "max_drawdown": max_dd,
            "fees_paid": sum((f.fee for f in result.fills), Decimal("0")),
            "fill_count": len(result.fills),
            "completed_round_trips": sum(f.action == "SELL" for f in result.fills),
            "ending_cash": final.cash,
            "ending_quantity": final.quantity,
            "ending_dividend_receivable": final.receivable,
            "dividends_paid": sum((a.amount for a in result.action_ledger if a.kind == "dividend_payment"), Decimal("0")),
            "rejected_orders": len(result.rejections),
            "pending_order": result.pending is not None,
        }


def chart(bars, result):
    width, height, pad = 960, 300, 40
    lo, hi = float(min(b.low for b in bars)), float(max(b.high for b in bars))
    span = hi - lo or 1
    def x(i): return pad + i * (width - 2 * pad) / max(1, len(bars) - 1)
    def y(p): return height - pad - (float(p) - lo) / span * (height - 2 * pad)
    parts = [f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Daily candles, confirmed retest levels and actual simulated fills">']
    parts.append(f'<text x="5" y="22">{hi:.2f}</text><text x="5" y="290">{lo:.2f}</text>')
    candle_width = min(10, (width - 2 * pad) / max(1, len(bars)) * .6)
    for i, b in enumerate(bars):
        color = "#18794e" if b.close >= b.open else "#bd3636"
        parts.append(f'<g><title>{b.date}: O {b.open} H {b.high} L {b.low} C {b.close}</title><line x1="{x(i)}" x2="{x(i)}" y1="{y(b.high)}" y2="{y(b.low)}" stroke="{color}"/><rect x="{x(i)-candle_width/2}" y="{min(y(b.open),y(b.close))}" width="{candle_width}" height="{max(1,abs(y(b.open)-y(b.close)))}" fill="{color}"/></g>')
    indices = {b.date: i for i, b in enumerate(bars)}
    for signal in result.signals:
        if signal.decision.level is not None:
            i, level = indices[signal.date], signal.decision.level
            parts.append(f'<line x1="{x(max(0,i-3))}" x2="{x(i)}" y1="{y(level)}" y2="{y(level)}" stroke="#8b5cf6" stroke-dasharray="4 3"><title>Frozen breakout level confirmed on {signal.date}: {level}</title></line>')
    for fill in result.fills:
        i = indices[fill.date]
        parts.append(f'<circle cx="{x(i)}" cy="{y(fill.reference_price)}" r="5" fill="#2563eb"><title>{html.escape(fill.action)} {fill.quantity} at {fill.price}, fee {fill.fee}; signal {fill.signal_date}</title></circle><text x="{x(i)+6}" y="{y(fill.reference_price)-8}">{fill.action[0]}</text>')
    parts.append('</svg>')
    return "".join(parts)


def make_html(bars, results, manifest):
    with localcontext(NUMERIC_CONTEXT):
        return _make_html(bars, results, manifest)


def _make_html(bars, results, manifest):
    escape = lambda value: html.escape(str(value))
    rows = []
    for name, result in results.items():
        m = metrics(result)
        rows.append(f'<tr><td>{escape(name)}</td><td>${m["final_equity"]:.2f}</td><td>{m["total_return"]:.2%}</td><td>{m["max_drawdown"]:.2%}</td><td>${m["fees_paid"]:.2f}</td><td>{m["completed_round_trips"]}</td></tr>')
    strategy = results["breakout_retest"]
    fills = "".join(f'<tr><td>{f.signal_date}</td><td>{f.date}</td><td>{f.action}</td><td>{f.quantity}</td><td>{f.price}</td><td>{f.fee}</td><td>{f.cash_after}</td><td>{escape(f.reason)}</td></tr>' for f in strategy.fills)
    rejected = "".join(f'<li>{r.date}: {escape(r.reason)}</li>' for r in strategy.rejections) or '<li>None</li>'
    provenance = manifest.get("provenance", {})
    quality = provenance.get("quality") or provenance.get("parent_provenance", {}).get("quality")
    data_note = ("Saved raw response and normalized bars were revalidated against a versioned exchange calendar. Ordinary dividends require matching explicit payment-date supplements; vendor split windows are rejected. Vendor revisions and missing vendor events remain unverified."
                 if quality else "This input has no exchange-calendar or corporate-action verification. Do not interpret it as market research evidence.")
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Research evidence — {escape(manifest['symbol'])}</title>
<style>body{{font:16px system-ui;margin:36px auto;padding:0 24px;max-width:1100px;color:#172b4d;background:#f5f7fb}}h1{{margin-bottom:8px}}section{{background:white;border:1px solid #dbe2ee;padding:20px;margin:20px 0;border-radius:8px}}table{{border-collapse:collapse;width:100%;font-size:14px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #dbe2ee}}svg{{width:100%;background:#fff}}svg text{{font-size:12px}}code{{overflow-wrap:anywhere}}.scroll{{overflow:auto}}.notice{{border-left:5px solid #bf7500}}</style>
<h1>Daily-bar research evidence</h1><p>{escape(manifest['symbol'])} · price history {bars[0].date} to {bars[-1].date} · {len(bars)} bars</p><p>Portfolio evaluation: {strategy.equity[0].date} to {strategy.equity[-1].date}. Earlier candles, if present, are indicator warm-up only.</p>
<section class="notice"><b>Engineering demonstration — not validated strategy evidence.</b><p>Data classification: {escape(manifest['data_kind'])}. This milestone does not implement walk-forward inference, multiple-testing correction, or broker execution. Costs are illustrative assumptions, not a broker fee schedule.</p></section>
<section><h2>Performance, including costs</h2><div class="scroll"><table><tr><th>Strategy</th><th>Final equity</th><th>Total return</th><th>Max drawdown</th><th>Fees</th><th>Round trips</th></tr>{''.join(rows)}</table></div><p>Buy-and-hold submits at the first eligible close with the same allocation and cost model; strategy entry dates can differ. Cash earns zero interest. Open holdings are marked to the final close; no invented final liquidation. All strategies have full ledgers in the CSV/JSON artifacts.</p></section>
<section><h2>Price and trade inspection</h2>{chart(bars, strategy)}<p>Hover over candles and markers for values. B/S = next-open fills; purple dashed segments mark confirmed retest levels, not historical order availability.</p></section>
<section><h2>Strategy fill ledger</h2><div class="scroll"><table><tr><th>Signal close</th><th>Fill open</th><th>Side</th><th>Quantity</th><th>Fill price</th><th>Fee</th><th>Cash after</th><th>Reason</th></tr>{fills}</table></div><p>Final pending signal: {escape(strategy.pending)}. Ending units: {strategy.equity[-1].quantity}.</p><h3>Rejected orders</h3><ul>{rejected}</ul></section>
<section><h2>Corporate actions</h2><p>Dividend entitlements enter equity on the ex-date using holdings before its open. Spendable cash arrives at the first supplied session after the payable date. Ending receivable: ${strategy.equity[-1].receivable:.2f}. See action_ledger.csv and actions.json for the records. Explicit as-traded splits adjust shares, entry prices and strategy history; fractional-lot outcomes are rejected.</p></section>
<section><h2>Execution assumptions</h2><p>One stock/ETF, USD, long-only, cash-funded. Decisions see completed bars only. Market orders fill at the next supplied session's open with adverse slippage and per-fill fees. Stops are close-based decisions, not intraday stop orders; overnight losses can exceed the threshold. Entry allocation is capped; appreciation is not automatically rebalanced.</p><p>{escape(data_note)}</p></section>
<section><h2>Reproduction</h2><p>Run ID: <code>{manifest['run_id']}</code></p><p>Dataset SHA-256: <code>{manifest['dataset_sha256']}</code></p><p>Source SHA-256: <code>{manifest['source_sha256']}</code></p><p>See manifest.json, results.json, fills.csv, equity.csv and input.csv beside this report.</p></section></html>'''


def save_bundle(output_root: Path, dataset: Dataset, results: dict[str, Result]):
    if "breakout_retest" not in results:
        raise ValueError("report needs a breakout_retest result")
    if any(r.bars_sha256 != dataset.bars_sha256 for r in results.values()):
        raise ValueError("results were not computed from this dataset")
    if any(r.actions_sha256 != dataset.actions_sha256 for r in results.values()):
        raise ValueError("results were not computed from these corporate actions")
    source_files, source_sha = checked_source()
    if any(r.source_sha256 != source_sha for r in results.values()):
        raise ValueError("source differs from code used for computation")
    manifest = {
        "schema_version": 3,
        "symbol": dataset.symbol,
        "data_kind": dataset.kind,
        "dataset_sha256": dataset.sha256,
        "bars_sha256": dataset.bars_sha256,
        "actions_sha256": dataset.actions_sha256,
        "actions_raw_sha256": digest(dataset.actions_raw),
        "provenance": json.loads(dataset.provenance_json),
        "source_sha256": source_sha,
        "python_version": platform.python_version(),
        "strategies": {name: {"execution_config": r.config, "strategy": json.loads(r.strategy_spec_json), "decision_start": r.decision_start}
                       for name, r in sorted(results.items())},
        "execution": "completed close -> next supplied session open; close-based exits; terminal mark",
        "validation_status": "engineering_only",
    }
    manifest["run_id"] = digest(canonical(manifest).encode())[:20]
    artifacts = {
        "input.csv": dataset.raw,
        "actions.json": dataset.actions_raw,
        "source_snapshot.json": canonical(source_files).encode(),
        "manifest.json": canonical(manifest).encode(),
        "results.json": canonical({name: {"metrics": metrics(r), "result": r} for name, r in sorted(results.items())}).encode(),
    }
    for filename, attr, columns in [
        ("fills.csv", "fills", ["signal_date", "date", "action", "quantity", "reference_price", "price", "notional", "fee", "cash_after", "quantity_after", "reason"]),
        ("equity.csv", "equity", ["date", "cash", "quantity", "close", "equity", "receivable"]),
        ("action_ledger.csv", "action_ledger", ["date", "event_date", "kind", "quantity", "amount", "cash_after", "receivable_after"]),
    ]:
        with io.StringIO(newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["strategy"] + columns)
            writer.writeheader()
            for name, r in sorted(results.items()):
                for record in getattr(r, attr):
                    writer.writerow({"strategy": name, **asdict(record)})
            artifacts[filename] = handle.getvalue().encode()
    artifacts["report.html"] = make_html(dataset.bars, dict(sorted(results.items())), manifest).encode()
    return publish(output_root, manifest["run_id"], artifacts)
