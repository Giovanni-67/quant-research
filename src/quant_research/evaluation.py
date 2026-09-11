"""Registered chronological diagnostics for fixed rules; no fitted model or p-values."""
import csv
import html
import io
import json
import platform
from datetime import date
from pathlib import Path

from .actions import action_records
from .data import Dataset
from .engine import run
from .models import Config
from .reporting import metrics, save_bundle
from .serialization import canonical, digest
from .source import checked_source
from .storage import publish
from .strategies import BreakoutConfig, research_strategies


def prefix_dataset(dataset: Dataset, end: date) -> Dataset:
    bars = [b for b in dataset.bars if b.date < end]
    handle = io.StringIO(newline="")
    writer = csv.writer(handle, lineterminator="\n")
    writer.writerow(["date", "open", "high", "low", "close", "volume"])
    writer.writerows((b.date, b.open, b.high, b.low, b.close, b.volume) for b in bars)
    selected = tuple(a for a in dataset.actions if a.effective_date < end)
    actions = canonical({"schema_version": 1, "symbol": dataset.symbol, "price_basis": "as_traded",
                         "events": action_records(selected)}).encode() if dataset.actions_raw else b""
    provenance = {"derived_from_dataset_sha256": dataset.sha256, "end_exclusive": str(end),
                  "parent_provenance": json.loads(dataset.provenance_json)}
    return Dataset(handle.getvalue().encode(), dataset.symbol, dataset.kind, canonical(provenance), actions)


def evaluate(root: Path, dataset: Dataset, split: date, config: Config = Config(),
             breakout: BreakoutConfig = BreakoutConfig()) -> Path:
    days = [b.date for b in dataset.bars]
    if split not in days:
        raise ValueError("evaluation split must be a supplied session")
    boundary = days.index(split)
    if boundary < max(breakout.lookback + 1, 21) or len(days) - boundary < 20:
        raise ValueError("need full indicator warm-up before split and at least 20 evaluation sessions")
    source_files, source_sha = checked_source()
    strategies = research_strategies(breakout)
    plan = {
        "schema_version": 1, "kind": "fixed_rule_chronological_diagnostic",
        "dataset_sha256": dataset.sha256, "actions_sha256": dataset.actions_sha256,
        "actions_raw_sha256": digest(dataset.actions_raw), "python_version": platform.python_version(),
        "provenance_sha256": digest(dataset.provenance_json.encode()), "symbol": dataset.symbol,
        "source_sha256": source_sha, "evaluation_start": str(split), "execution_config": config,
        "candidates": {name: {"implementation": f"{type(s).__module__}.{type(s).__qualname__}",
                              "parameters": getattr(s, "config", None)} for name, s in strategies.items()},
        "rules": {"selection": "none; disclose all candidates", "fitting": "none; fixed rules",
                  "evaluation_initial_state": "fresh cash; no earlier orders or positions",
                  "warmup": "earlier bars available as causal indicator history; no earlier decisions",
                  "first_possible_fill": "session after evaluation_start close",
                  "inference": "none; no significance, walk-forward optimization or multiple-testing claim",
                  "holdout_status": "historical diagnostic; prior human exposure cannot be verified"},
    }
    identity = digest(canonical(plan).encode())[:20]
    # Persist candidate family BEFORE any candidate simulation. Failures leave a record.
    publish(root / "plans", identity, {"plan.json": canonical(plan).encode(),
                                       "source_snapshot.json": canonical(source_files).encode()})
    development = prefix_dataset(dataset, split)
    development_results = {name: run(development.bars, strategy, config, actions=development.actions)
                           for name, strategy in strategies.items()}
    evaluation_results = {name: run(dataset.bars, strategy, config, actions=dataset.actions, decision_start=split)
                          for name, strategy in research_strategies(breakout).items()}
    dev_bundle = save_bundle(root / "runs", development, development_results)
    eval_bundle = save_bundle(root / "runs", dataset, evaluation_results)
    comparison = {name: {"development": metrics(development_results[name]), "evaluation": metrics(result)}
                  for name, result in evaluation_results.items()}
    rows = []
    for name, sections in comparison.items():
        for section, m in sections.items():
            rows.append(f'<tr><td>{html.escape(name)}</td><td>{section}</td><td>{m["total_return"]:.2%}</td>'
                        f'<td>{m["max_drawdown"]:.2%}</td><td>{m["completed_round_trips"]}</td></tr>')
    report = f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Chronological research comparison</title><style>body{{font:16px system-ui;max-width:1000px;margin:40px auto;padding:20px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #ccc}}table{{border-collapse:collapse}}</style>
<h1>{html.escape(dataset.symbol)}: chronological diagnostic</h1><p>Evaluation decisions begin {split}; fresh ${config.initial_cash} cash. Earlier prices warm indicators, with no earlier orders. All three hypotheses and both baselines are shown.</p>
<p><strong>This is not evidence of a statistically validated edge.</strong> There is no parameter fitting, winner selection, walk-forward optimization, or significance test. Prior exposure to this historical period is unknown. Inspecting it consumes it as a future holdout.</p>
<table><tr><th>Strategy</th><th>Period</th><th>Return</th><th>Drawdown</th><th>Round trips</th></tr>{''.join(rows)}</table>
<p><a href="../../runs/{dev_bundle.name}/report.html">Development ledger</a> · <a href="../../runs/{eval_bundle.name}/report.html">Evaluation ledger</a></p>
<p>Unequal periods are not directly comparable; returns are not annualized. Open positions remain marked. Low or zero trade counts cannot establish an edge.</p></html>'''
    return publish(root / "comparisons", identity, {"plan.json": canonical(plan).encode(),
        "comparison.json": canonical(comparison).encode(), "report.html": report.encode(),
        "bundles.json": canonical({"development": dev_bundle.name, "evaluation": eval_bundle.name}).encode()})
