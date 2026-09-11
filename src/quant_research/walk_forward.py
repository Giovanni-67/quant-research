"""Rolling historical selection diagnostics, with isolated accounts per test fold."""
import csv
import html
import io
import json
import platform
from dataclasses import dataclass, replace
from datetime import timedelta
from decimal import Decimal, localcontext
from pathlib import Path

from .data import Dataset
from .engine import run
from .evaluation import prefix_dataset
from .models import Config, finite
from .reporting import metrics, save_bundle
from .serialization import NUMERIC_CONTEXT, canonical, digest
from .source import checked_source
from .storage import publish
from .strategies import BreakoutConfig, research_strategies
from .uncertainty import NAMES, UncertaintyConfig, paired_sample, analyze

ACTIVE = NAMES


@dataclass(frozen=True)
class WalkForwardConfig:
    train_sessions: int = 80
    test_sessions: int = 40
    gap_sessions: int = 5
    min_training_round_trips: int = 3
    cost_multipliers: tuple[Decimal, ...] = (Decimal(1), Decimal(2), Decimal(4))

    def __post_init__(self):
        for name in ("train_sessions", "test_sessions", "gap_sessions", "min_training_round_trips"):
            value = getattr(self, name)
            minimum = 0 if name == "gap_sessions" else 1
            if type(value) is not int or value < minimum:
                raise ValueError(f"{name} must be an integer >= {minimum}")
        if self.train_sessions < 2 or self.test_sessions < 2:
            raise ValueError("training/test windows need at least two sessions for next-open execution")
        if type(self.cost_multipliers) is not tuple or not self.cost_multipliers:
            raise ValueError("cost multipliers must be a nonempty immutable tuple")
        for value in self.cost_multipliers:
            finite(value, "cost multiplier")
        if self.cost_multipliers[0] != 1 or any(b <= a for a, b in zip(self.cost_multipliers, self.cost_multipliers[1:])):
            raise ValueError("cost multipliers must start at 1 and increase strictly")


@dataclass(frozen=True)
class Fold:
    number: int
    train_start: int
    train_end: int  # Exclusive indices, not dates.
    test_start: int
    test_end: int


def folds_for(count: int, config: WalkForwardConfig, warmup: int = 21) -> tuple[Fold, ...]:
    if type(count) is not int or type(warmup) is not int or warmup < 1:
        raise ValueError("count and warmup must be integers; warmup must be positive")
    first = warmup + config.train_sessions + config.gap_sessions
    folds = []
    for start in range(first, count, config.test_sessions):
        end = min(count, start + config.test_sessions)
        if end - start < 2:
            break  # A singleton tail cannot execute a first-close decision.
        train_end = start - config.gap_sessions
        folds.append(Fold(len(folds) + 1, train_end - config.train_sessions, train_end, start, end))
    if len(folds) < 2:
        raise ValueError("walk-forward needs at least two test folds after warm-up, training and gap")
    return tuple(folds)


@dataclass(frozen=True)
class TrainingScore:
    name: str
    net_return: Decimal
    completed_round_trips: int

    def __post_init__(self):
        finite(self.net_return, "training net return")
        if self.name not in ACTIVE or type(self.completed_round_trips) is not int or self.completed_round_trips < 0:
            raise ValueError("invalid training score")


def select_candidate(scores: tuple[TrainingScore, ...], minimum: int) -> str:
    """Pure selector: no bars, evaluation metrics, filesystem or LLM input."""
    if type(minimum) is not int or minimum < 1:
        raise ValueError("minimum completed trades must be a positive integer")
    if len(scores) != len(ACTIVE) or {s.name for s in scores} != set(ACTIVE):
        raise ValueError("selection requires exactly the registered three active candidates")
    eligible = [s for s in scores if s.completed_round_trips >= minimum and s.net_return > 0]
    if not eligible:
        return "cash"
    # Highest net marked return; exact ties break by ascending stable candidate name.
    with localcontext(NUMERIC_CONTEXT):
        return sorted(eligible, key=lambda s: (-s.net_return, s.name))[0].name


def _through(dataset: Dataset, count: int) -> Dataset:
    return prefix_dataset(dataset, dataset.bars[count-1].date + timedelta(days=1))


def _window_results(dataset: Dataset, start: int, config: Config, breakout: BreakoutConfig):
    return {name: run(dataset.bars, strategy, config, actions=dataset.actions,
                      decision_start=dataset.bars[start].date)
            for name, strategy in research_strategies(breakout).items()}


def walk_forward(root: Path, dataset: Dataset, execution: Config = Config(),
                 protocol: WalkForwardConfig = WalkForwardConfig(),
                 breakout: BreakoutConfig = BreakoutConfig(), *,
                 uncertainty: UncertaintyConfig | None = None) -> Path:
    with localcontext(NUMERIC_CONTEXT):
        return _walk_forward(root, dataset, execution, protocol, breakout, uncertainty)


def _walk_forward(root, dataset, execution, protocol, breakout, uncertainty):
    folds = folds_for(len(dataset.bars), protocol, max(21, breakout.lookback + 1))
    cost_configs = [(multiplier, replace(execution, fee_bps=execution.fee_bps * multiplier,
                                         slippage_bps=execution.slippage_bps * multiplier))
                    for multiplier in protocol.cost_multipliers]
    source_files, source_sha = checked_source()
    dates = [b.date for b in dataset.bars]
    plan = {
        "schema_version": 1, "kind": "rolling_selection_independent_fold_diagnostic",
        "symbol": dataset.symbol, "data_kind": dataset.kind,
        "dataset_sha256": dataset.sha256, "actions_sha256": dataset.actions_sha256,
        "actions_raw_sha256": digest(dataset.actions_raw),
        "provenance_sha256": digest(dataset.provenance_json.encode()),
        "source_sha256": source_sha, "python_version": platform.python_version(),
        "protocol": protocol, "execution": execution,
        "uncertainty": uncertainty,
        "uncertainty_family": {"candidates": ACTIVE, "benchmark": "buy_and_hold_same_allocation",
            "cost_scenario": "base_only", "multiplicity": "all candidate/block-length pairs; Holm; withheld cases retain family membership",
            "estimand": "mean paired daily arithmetic return difference within test folds; omit first-day zero",
            "adaptive_selector_inference": "not performed"} if uncertainty else None,
        "candidates": {name: {"implementation": f"{type(s).__module__}.{type(s).__qualname__}",
                              "parameters": getattr(s, "config", None)}
                       for name, s in research_strategies(breakout).items()},
        "folds": [{"indices": fold, "train_start": dates[fold.train_start],
                   "train_last": dates[fold.train_end-1], "test_start": dates[fold.test_start],
                   "test_last": dates[fold.test_end-1]} for fold in folds],
        "unused_tail_sessions": len(dates) - folds[-1].test_end,
        "rules": {
            "selection": "positive training net marked return; minimum closed trades; highest return; name tie-break; otherwise cash",
            "comparators": "buy-and-hold and cash disclosed; buy-and-hold is not selectable",
            "score": "ending marked equity / initial cash - 1; includes incurred costs and dividends; no hypothetical liquidation",
            "gap": "excluded from training scores; completed gap bars may warm test indicators; not a general label-purging scheme",
            "warmup": "price history before each decision window; no prior decisions, positions or pending orders",
            "accounts": "fresh cash in every training/test/scenario run; no inter-fold transfers or synthetic liquidation",
            "test_windows": "non-overlapping; partial final fold retained if >= 2 sessions; later training may use earlier test dates",
            "cost_stress": "scale fee and slippage bps, keep training selection fixed; replay all candidates for disclosure",
            "inference": "none for adaptive selector; optional exploratory fixed-candidate diagnostics are separate; no stitched account curve or validated edge",
            "holdout": "historical diagnostic; prior exposure unknown; registry does not cover external/deleted trials",
        },
    }
    identity = digest(canonical(plan).encode())[:20]
    publish(root / "plans", identity, {"plan.json": canonical(plan).encode(),
                                      "source_snapshot.json": canonical(source_files).encode()})
    records, samples = [], []
    for fold in folds:
        # The training engine physically receives only data through train_end.
        training_data = _through(dataset, fold.train_end)
        training = _window_results(training_data, fold.train_start, execution, breakout)
        train_metrics = {name: metrics(result) for name, result in training.items()}
        scores = tuple(TrainingScore(name, train_metrics[name]["total_return"],
                                     train_metrics[name]["completed_round_trips"]) for name in ACTIVE)
        selected = select_candidate(scores, protocol.min_training_round_trips)
        train_bundle = save_bundle(root / "runs", training_data, training)
        choice = {"fold": fold.number, "selected": selected, "scores": scores,
                  "minimum_completed_trades": protocol.min_training_round_trips,
                  "selection_as_of": dates[fold.train_end-1],
                  "training_bars_sha256": training_data.bars_sha256,
                  "training_actions_sha256": training_data.actions_sha256,
                  "training_bundle": train_bundle.name}
        choice_id = digest(canonical({"plan_id": identity, "choice": choice}).encode())[:20]
        # A successful choice is persisted before reading test metrics, even if test fails.
        publish(root / "selections", choice_id, {"selection.json": canonical(choice).encode(),
                                                "plan_id.json": canonical(identity).encode()})
        testing_data = _through(dataset, fold.test_end)
        scenarios = []
        for multiplier, cost_config in cost_configs:
            testing = _window_results(testing_data, fold.test_start, cost_config, breakout)
            if uncertainty is not None and multiplier == 1:
                samples.append(paired_sample(testing))
            test_bundle = save_bundle(root / "runs", testing_data, testing)
            scenarios.append({"cost_multiplier": multiplier, "selected": selected,
                              "test_bundle": test_bundle.name,
                              "metrics": {name: metrics(result) for name, result in testing.items()}})
        records.append({"fold": fold, "selection": choice, "selection_id": choice_id,
                        "training_metrics": train_metrics, "scenarios": scenarios})
    summary = {"fold_count": len(folds), "test_sessions": sum(f.test_end-f.test_start for f in folds),
               "unused_tail_sessions": plan["unused_tail_sessions"],
               "selection_counts": {name: sum(r["selection"]["selected"] == name for r in records)
                                    for name in (*ACTIVE, "cash")},
               "aggregation": "none; fold accounts reset, so do not compound these returns"}
    artifacts = {"plan.json": canonical(plan).encode(), "folds.json": canonical(records).encode(),
                 "summary.json": canonical(summary).encode()}
    output = io.StringIO(newline="")
    columns = ["fold", "train_start", "train_last", "test_start", "test_last", "cost_multiplier",
               "selected", "candidate", "net_return", "max_drawdown", "completed_round_trips",
               "ending_quantity", "ending_receivable"]
    writer = csv.DictWriter(output, fieldnames=columns)
    writer.writeheader()
    for record in records:
        fold = record["fold"]
        for scenario in record["scenarios"]:
            for name, m in scenario["metrics"].items():
                writer.writerow(dict(zip(columns, [fold.number, dates[fold.train_start], dates[fold.train_end-1],
                    dates[fold.test_start], dates[fold.test_end-1], scenario["cost_multiplier"],
                    scenario["selected"], name, m["total_return"], m["max_drawdown"],
                    m["completed_round_trips"], m["ending_quantity"], m["ending_dividend_receivable"]])))
    artifacts["fold_metrics.csv"] = output.getvalue().encode()
    if uncertainty is not None:
        diagnostic = analyze(tuple(samples), uncertainty)
        artifacts["paired_returns.json"] = canonical(samples).encode()
        artifacts["uncertainty.json"] = canonical(diagnostic).encode()
        artifacts["uncertainty.html"] = _uncertainty_report(diagnostic).encode()
    artifacts["report.html"] = _report(plan, records, summary).encode()
    return publish(root / "comparisons", identity, artifacts)


def _report(plan, records, summary):
    rows, details = [], []
    for info, record in zip(plan["folds"], records):
        selected = record["selection"]["selected"]
        fold = record["fold"]
        candidate_rows = []
        for scenario in record["scenarios"]:
            m = scenario["metrics"][selected]
            benchmark = scenario["metrics"]["buy_and_hold_same_allocation"]
            rows.append(f'<tr><td>{fold.number}</td><td>{info["test_start"]}–{info["test_last"]}</td>'
                        f'<td>{html.escape(selected)}</td><td>{scenario["cost_multiplier"]}×</td>'
                        f'<td>{m["total_return"]:.3%}</td><td>{m["max_drawdown"]:.3%}</td>'
                        f'<td>{m["completed_round_trips"]}</td><td>{benchmark["total_return"]:.3%}</td>'
                        f'<td><a href="../../runs/{scenario["test_bundle"]}/report.html">Ledger</a></td></tr>')
            for name, candidate_metrics in scenario["metrics"].items():
                candidate_rows.append(f'<tr><td>{html.escape(name)}</td><td>{scenario["cost_multiplier"]}×</td>'
                                      f'<td>{candidate_metrics["total_return"]:.3%}</td>'
                                      f'<td>{candidate_metrics["max_drawdown"]:.3%}</td>'
                                      f'<td>{candidate_metrics["completed_round_trips"]}</td></tr>')
        score_rows = ''.join(f'<tr><td>{s.name}</td><td>{s.net_return:.3%}</td>'
                             f'<td>{s.completed_round_trips}</td><td>{"yes" if s.completed_round_trips >= plan["protocol"].min_training_round_trips and s.net_return > 0 else "no"}</td></tr>'
                             for s in record["selection"]["scores"])
        details.append(f'<details><summary>Fold {fold.number}: why {html.escape(selected)} was selected</summary>'
                       f'<p>Training {info["train_start"]}–{info["train_last"]}; test begins {info["test_start"]}. '
                       f'Minimum closed trades: {plan["protocol"].min_training_round_trips}. Only positive training returns qualify.</p>'
                       f'<table><tr><th>Candidate</th><th>Training return</th><th>Closed trades</th><th>Eligible</th></tr>{score_rows}</table>'
                       f'<p><a href="../../selections/{record["selection_id"]}/selection.json">Frozen selection</a> · '
                       f'<a href="../../runs/{record["selection"]["training_bundle"]}/report.html">Training ledger</a></p>'
                       f'<h3>All test candidates and cost scenarios</h3><p>These later results were unavailable to the selector.</p>'
                       f'<div class="scroll"><table><tr><th>Candidate</th><th>Costs</th><th>Test return</th><th>Drawdown</th><th>Closed trades</th></tr>{"".join(candidate_rows)}</table></div></details>')
    uncertainty_link = '<p><a href="uncertainty.html">Fixed-candidate uncertainty and multiple-testing diagnostics</a></p>' if plan['uncertainty'] else ''
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Walk-forward research — {html.escape(plan['symbol'])}</title><style>body{{font:16px system-ui;max-width:1200px;margin:32px auto;padding:20px;color:#172b4d}}table{{border-collapse:collapse}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #ddd}}.scroll{{overflow:auto}}details{{padding:16px;background:#f4f6fa;margin:14px 0}}.note{{border-left:5px solid #b97400;padding:16px;background:#fff7e8}}</style>
<h1>{html.escape(plan['symbol'])}: walk-forward research</h1>
{uncertainty_link}
<p>{summary['fold_count']} independent test folds · {summary['test_sessions']} test sessions · {summary['unused_tail_sessions']} unused tail sessions</p>
<p class="note"><strong>Historical engineering diagnostic, not a validated trading edge.</strong> Choices use earlier data only, but this history has already been inspected. Fold accounts reset to fresh cash. Returns must not be compounded into a live-account claim. The adaptive selector has no significance test; optional fixed-candidate diagnostics are separate.</p>
<p>Training: {plan['protocol'].train_sessions} sessions; gap: {plan['protocol'].gap_sessions}; test: up to {plan['protocol'].test_sessions}. Costs are assumptions. Cost stress preserves the originally selected candidate. All candidates' test metrics are in <a href="fold_metrics.csv">fold_metrics.csv</a>.</p>
<div class="scroll"><table><tr><th>Fold</th><th>Test window</th><th>Selected</th><th>Costs</th><th>Net return</th><th>Drawdown</th><th>Closed trades</th><th>Buy-and-hold</th><th>Evidence</th></tr>{''.join(rows)}</table></div>
<h2>Selection evidence</h2>{''.join(details)}
<p>Open positions and unpaid dividends remain marked in their own fold. No boundary sale or transfer is invented. Shared training windows mean fold outcomes are not independent statistical observations.</p></html>'''


def _uncertainty_report(diagnostic):
    rows = []
    for row in diagnostic['rows']:
        interval = row['exploratory_percentile_interval']
        interval_text = f'{interval[0]:.5%} to {interval[1]:.5%}' if interval else 'Unavailable'
        corrected = f'{row["holm_pvalue"]:.4f}' if row['holm_pvalue'] is not None else 'Withheld'
        reasons = ', '.join(row['withheld_reasons']) or 'Exploratory estimate; assumptions apply'
        rows.append(f'<tr><td>{row["candidate"]}</td><td>{row["block_length"]}</td>'
                    f'<td>{row["mean_daily_difference"]:.5%}</td><td>{interval_text}</td>'
                    f'<td>{corrected}</td><td>{html.escape(reasons)}</td></tr>')
    limits = ''.join(f'<li>{html.escape(reason)}</li>' for reason in diagnostic['limitations'])
    return f'''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width">
<title>Exploratory uncertainty</title><style>body{{font:16px system-ui;max-width:1200px;margin:32px auto;padding:20px}}td,th{{padding:10px;text-align:left;border-bottom:1px solid #ddd}}table{{border-collapse:collapse}}.scroll{{overflow:auto}}</style>
<h1>Fixed-candidate uncertainty diagnostics</h1><p><a href="report.html">Back to walk-forward results</a></p>
<p><strong>Exploratory, not validated strategy evidence.</strong> Base costs only. This analyzes the three fixed candidates relative to same-allocation buy-and-hold, not the adaptive selector. Family size: {diagnostic['family_size']} candidate/block-length pairs.</p>
<p>Values are mean daily arithmetic return differences, not annualized returns or total account growth. Intervals are marginal percentile intervals from paired circular blocks. Withheld p-values mean minimum-data or nondegeneracy checks failed. Those checks are engineering safeguards, not a power analysis.</p>
<div class="scroll"><table><tr><th>Candidate</th><th>Block sessions</th><th>Mean daily difference</th><th>Exploratory interval</th><th>Holm p-value</th><th>Status</th></tr>{''.join(rows)}</table></div>
<ul>{limits}</ul><p>See uncertainty.json, paired_returns.json and the registered plan for exact values, seeds, thresholds and assumptions.</p></html>'''
