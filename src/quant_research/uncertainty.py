"""Exploratory fixed-family bootstrap diagnostics, never a trading approval gate."""
from dataclasses import dataclass
from datetime import date
from decimal import localcontext
import math
import random

from .models import Result
from .serialization import NUMERIC_CONTEXT

NAMES = ("bollinger_swing", "breakout_retest", "trend_swing")
BENCHMARK = "buy_and_hold_same_allocation"


@dataclass(frozen=True)
class UncertaintyConfig:
    repetitions: int = 1999
    seed: int = 73421
    block_lengths: tuple[int, ...] = (3, 5, 10)
    min_sessions: int = 100
    min_blocks: int = 20
    min_round_trips: int = 20
    alpha: float = .05

    def __post_init__(self):
        for name in ("repetitions", "min_sessions", "min_blocks", "min_round_trips"):
            if type(getattr(self, name)) is not int or getattr(self, name) < 1:
                raise ValueError(f"{name} must be a positive integer")
        if self.repetitions < 99 or type(self.seed) is not int or self.seed < 0:
            raise ValueError("need at least 99 replicates and a nonnegative integer seed")
        if type(self.block_lengths) is not tuple or not self.block_lengths or any(type(x) is not int or x < 1 for x in self.block_lengths):
            raise ValueError("block lengths must be a nonempty tuple of positive integers")
        if tuple(sorted(set(self.block_lengths))) != self.block_lengths:
            raise ValueError("block lengths must increase strictly")
        if type(self.alpha) is not float or not math.isfinite(self.alpha) or not 0 < self.alpha < 1:
            raise ValueError("alpha must be a float in (0, 1)")


@dataclass(frozen=True)
class FoldSample:
    dates: tuple[date, ...]
    # Paired daily arithmetic return differentials, columns in NAMES order.
    differences: tuple[tuple[float, ...], ...]
    round_trips: tuple[int, ...]

    def __post_init__(self):
        if type(self.dates) is not tuple or type(self.differences) is not tuple or not self.dates or len(self.dates) != len(self.differences):
            raise ValueError("fold needs aligned immutable dates and differences")
        if any(type(d) is not date for d in self.dates) or any(b <= a for a, b in zip(self.dates, self.dates[1:])):
            raise ValueError("fold dates must be strictly increasing")
        if any(type(row) is not tuple or len(row) != len(NAMES) or any(type(v) is not float or not math.isfinite(v) for v in row) for row in self.differences):
            raise ValueError("fold needs three finite float differences per date")
        if type(self.round_trips) is not tuple or len(self.round_trips) != len(NAMES) or any(type(n) is not int or n < 0 for n in self.round_trips):
            raise ValueError("fold needs three nonnegative integer trade counts")


def paired_sample(results: dict[str, Result]) -> FoldSample:
    """Exclude artificial first-day zero; never create a return between fold accounts."""
    if any(name not in results for name in (*NAMES, BENCHMARK)):
        raise ValueError("paired comparison needs every fixed candidate and benchmark")
    benchmark = results[BENCHMARK]
    dates = tuple(p.date for p in benchmark.equity)
    if len(dates) < 2:
        raise ValueError("at least two aligned equity points required")
    with localcontext(NUMERIC_CONTEXT):
        for name in (*NAMES, BENCHMARK):
            result = results[name]
            if (tuple(p.date for p in result.equity) != dates or result.config != benchmark.config or
                result.bars_sha256 != benchmark.bars_sha256 or result.actions_sha256 != benchmark.actions_sha256 or
                result.source_sha256 != benchmark.source_sha256 or result.decision_start != benchmark.decision_start):
                raise ValueError("paired results must have identical sessions, input, source and execution assumptions")
            if any(p.equity <= 0 or not p.equity.is_finite() for p in result.equity):
                raise ValueError("daily returns require finite positive equity")
        rows = []
        for i in range(1, len(dates)):
            benchmark_return = benchmark.equity[i].equity / benchmark.equity[i-1].equity - 1
            rows.append(tuple(float(results[name].equity[i].equity / results[name].equity[i-1].equity - 1 - benchmark_return) for name in NAMES))
        return FoldSample(dates[1:], tuple(rows), tuple(sum(f.action == "SELL" for f in results[name].fills) for name in NAMES))


def holm(pvalues: tuple[float, ...]) -> tuple[float, ...]:
    """Step-down Bonferroni adjustment; guarantees require valid input p-values."""
    if not pvalues or any(type(p) is not float or not math.isfinite(p) or not 0 <= p <= 1 for p in pvalues):
        raise ValueError("p-values must be finite floats in [0, 1]")
    order = sorted(range(len(pvalues)), key=lambda i: (pvalues[i], i))
    adjusted, running = [0.] * len(order), 0.
    for rank, index in enumerate(order):
        running = max(running, min(1., (len(order)-rank) * pvalues[index]))
        adjusted[index] = running
    return tuple(adjusted)


def circular_indices(length: int, block: int, rng: random.Random) -> tuple[int, ...]:
    if type(length) is not int or type(block) is not int or not 1 <= block <= length:
        raise ValueError("block must fit in the fold")
    indices = []
    while len(indices) < length:
        start = rng.randrange(length)
        indices.extend((start + j) % length for j in range(min(block, length-len(indices))))
    return tuple(indices)


def _quantile(sorted_values, q):
    at = (len(sorted_values)-1) * q
    lo = int(at)
    hi = min(lo+1, len(sorted_values)-1)
    return sorted_values[lo] + (at-lo) * (sorted_values[hi]-sorted_values[lo])


def analyze(samples: tuple[FoldSample, ...], config: UncertaintyConfig = UncertaintyConfig()) -> dict:
    if type(samples) is not tuple or not samples or any(type(s) is not FoldSample for s in samples):
        raise ValueError("need immutable fold samples")
    if any(b.dates[0] <= a.dates[-1] for a, b in zip(samples, samples[1:])):
        raise ValueError("fold dates must be ordered and non-overlapping")
    rows = tuple(row for sample in samples for row in sample.differences)
    total = len(rows)
    observed = tuple(math.fsum(row[j] for row in rows)/total for j in range(len(NAMES)))
    counts = tuple(sum(s.round_trips[j] for s in samples) for j in range(len(NAMES)))
    outcomes = []
    for block in config.block_lengths:
        nominal_blocks = sum(len(s.differences)//block for s in samples)
        window_reasons = []
        if total < config.min_sessions: window_reasons.append("too_few_sessions")
        if nominal_blocks < config.min_blocks: window_reasons.append("too_few_nominal_blocks")
        if any(len(s.differences) < 2*block for s in samples): window_reasons.append("fold_shorter_than_two_blocks")
        draws = [[] for _ in NAMES]
        # Intervals may be exploratory even with sparse trades; p-values are withheld.
        if not window_reasons:
            rng = random.Random(config.seed + block)
            for _ in range(config.repetitions):
                selected_rows = []
                for sample in samples:
                    # All strategy columns share indices, preserving paired dependence.
                    selected_rows.extend(sample.differences[i] for i in circular_indices(len(sample.differences), block, rng))
                for j in range(len(NAMES)):
                    draws[j].append(math.fsum(row[j] for row in selected_rows)/total)
        for j, name in enumerate(NAMES):
            reasons = list(window_reasons)
            if counts[j] < config.min_round_trips: reasons.append("too_few_completed_trades")
            constant = all(row[j] == rows[0][j] for row in rows)
            if constant: reasons.append("constant_differential")
            distribution = sorted(draws[j])
            collapsed = bool(distribution) and distribution[0] == distribution[-1]
            if collapsed and not constant: reasons.append("degenerate_bootstrap")
            interval = None
            if distribution and not constant and not collapsed:
                interval = [_quantile(distribution, config.alpha/2), _quantile(distribution, 1-config.alpha/2)]
            # Center bootstrap mean under H0 E[difference] = 0, test one-sided > 0.
            pvalue = ((1 + sum(v-observed[j] >= observed[j] for v in distribution)) / (config.repetitions+1)) if not reasons else None
            outcomes.append({"candidate": name, "block_length": block, "sessions": total,
                "nominal_blocks": nominal_blocks, "completed_round_trips": counts[j],
                "mean_daily_difference": observed[j], "exploratory_percentile_interval": interval,
                "raw_pvalue": pvalue, "withheld_reasons": reasons})
    # Withheld cases stay in the registered family as non-rejections, not deleted tests.
    corrected = holm(tuple(row["raw_pvalue"] if row["raw_pvalue"] is not None else 1. for row in outcomes))
    for row, adjusted in zip(outcomes, corrected):
        row["holm_pvalue"] = adjusted if row["raw_pvalue"] is not None else None
        row["exploratory_reject_null"] = row["raw_pvalue"] is not None and adjusted <= config.alpha
    return {"status": "exploratory_not_validated", "family_size": len(outcomes), "config": config,
            "benchmark": BENCHMARK, "cost_scenario": "base_only", "rows": outcomes,
            "estimand": "session-weighted mean of fixed-candidate minus benchmark daily arithmetic returns within reset test accounts",
            "limitations": ["not inference for the adaptive selector", "prior historical exposure and external trials not corrected",
                "circular blocks assume useful local stationarity; fold boundaries and longer dependence not modeled",
                "nominal block count is not an estimated effective sample size",
                "Holm correction does not repair invalid bootstrap assumptions or repeated experiment selection",
                "percentile intervals are marginal exploratory intervals, not simultaneous familywise intervals"]}
