# Exploratory uncertainty contract — v0.5, 2026-09-10

This adds a reproducible uncertainty diagnostic for the fixed candidate family.
It does not validate the adaptive selector, authorize trading, or undo prior
inspection of the historical data. The data engine remains the numerical authority;
no LLM calculates a return, interval or p-value.

## The quantity being studied

For each fixed strategy and its same-allocation buy-and-hold comparator, compute
daily arithmetic returns from adjacent marked equity observations within each test
fold. Subtract the benchmark return from the candidate return on the same date.
The estimator is the session-weighted mean of those paired differences.

The first equity point of each test fold is initial cash before any fill. Omit
that artificial first-day zero return. Do not calculate returns between the end
of one reset account and the beginning of another. The 144 test sessions in the
saved study therefore supply 140 return observations across four folds.

This mean daily difference is not annualized alpha, total return, dollar profit,
a stitched portfolio return or a comparison at equal time-varying market exposure.
Each candidate's realized exposure may differ from buy-and-hold. Open positions and
dividend receivables are already included in engine equity; the statistics module
does not independently reconstruct financial accounting.

The pairing contract checks identical sessions, input/action/source identities,
execution configurations and decision starts. All equity must be finite and positive.
Money remains Decimal in the engine. The statistics layer converts final daily
differences to finite binary floats and uses `math.fsum` for summation. Python version,
source, inputs, seeds and settings are recorded for reproducibility.

## Resampling assumptions

Within each fold, draw fixed-length circular blocks of return rows, retaining the
original fold length. Sample the same row indices for all candidates, preserving
their paired relationship. Blocks wrap within a fold, never into another account.
Each replicate retains the original number of rows from each fold.

Use block lengths 3, 5 and 10, 1,999 replicates and seed 73421 (plus the block length
for its independent RNG stream). Report every block-length result. Percentile
intervals use linear interpolation at the 2.5th and 97.5th percentiles of the
resampled means. They are marginal exploratory 95% intervals, not simultaneous
familywise confidence intervals.

The approach assumes local dependence can usefully be represented by these blocks
and that sampling within each fold is meaningful. It does not preserve dependence
across fold boundaries or beyond the chosen block length. Nonstationarity, sparse
strategy activity, structural breaks and very few folds can invalidate its inference.
The recorded thresholds are engineering safeguards, not proof of these assumptions.

The choice of circular blocks was informed by the
[arch time-series bootstrap documentation](https://bashtage.github.io/arch/bootstrap/timeseries-bootstraps.html),
which describes fixed-length blocks with end-to-start wrapping. The implementation
uses Python's local `random.Random` instance; it does not change global random state
or require the arch package. It is not Hansen's SPA test or White's Reality Check.

## P-values, withheld cases and the declared family

The exploratory one-sided null is mean paired return difference <= 0. For each
candidate, center the bootstrap mean by subtracting its observed mean and compare
that null-centered draw with the observed mean. Count upper-tail exceedances with
the plus-one convention `(1 + exceedances) / (replicates + 1)`, avoiding a reported
zero Monte Carlo p-value. This is an approximate, unstudentized centered-bootstrap
test, not a finite-sample distribution-free guarantee.

Withhold p-values when any of these fail:

- At least 100 within-fold return observations.
- At least 20 nominal blocks, computed as the sum of floor(fold length / block length).
- Every fold has at least two blocks' worth of observations.
- At least 20 completed test round trips for the fixed candidate, summed across folds.
- The candidate differential and bootstrap distribution are nonconstant.

Nominal blocks are not an estimated effective sample size. Twenty trades are not
necessarily independent or sufficient for a reliable conclusion. Increasing these
counts cannot repair selection bias or invalid resampling assumptions. If only the
trade-count gate fails, the program may show an explicitly exploratory interval while
withholding the p-value. Short-window and degenerate cases also withhold the interval.

All three strategies multiplied by all three block lengths form one family of nine
comparisons. Apply Holm's step-down Bonferroni adjustment across that entire family.
Withheld cases contribute a non-rejection placeholder of 1 internally, preserving
the family size, while their displayed p-values remain unavailable. Cost stress
scenarios and the adaptive selector are outside this inference and are labeled so.

The [statsmodels multiple-testing documentation](https://www.statsmodels.org/stable/generated/statsmodels.stats.multitest.multipletests.html)
documents Holm's method. The local implementation is checked against hand-calculated
cases, ties, original input order and invalid values. Holm's error-control guarantee
requires valid input p-values; it does not make approximate bootstrap inputs exact,
correct previous tuning, or cover unrecorded experiments.

An `exploratory_reject_null` field can be true in eligible synthetic examples. It is
never consumed by the selector, engine, risk sizing or any trading path. It must not
be interpreted as a strategy approval flag.

## Current evidence

The unchanged XLF protocol still selects cash in all four folds. The fixed candidates
complete two Bollinger trades, one breakout/retest trade and four trend trades across
their reset test accounts. All nine p-values are withheld due to insufficient trade
counts; the 10-session blocks also fail the nominal-block minimum. The intervals
available for block lengths 3 and 5 span zero for every candidate.

This study remains inconclusive. Neither the negative observed mean differences nor
the exploratory intervals establish future performance or a reliable trading edge.
No eligibility threshold was lowered to turn this outcome into a favorable result.

Comparison ID: `d4e9b3694d2a11e12831`.

[Walk-forward report](../research-results-v5/comparisons/d4e9b3694d2a11e12831/report.html) ·
[Uncertainty report](../research-results-v5/comparisons/d4e9b3694d2a11e12831/uncertainty.html).

Exact settings, paired observations and diagnostics are saved alongside the reports.
They are bound to the same pre-simulation experiment plan and checksummed artifact
bundle. Repeating the command verifies computed artifacts byte-for-byte.

## Verification and remaining work

The suite now contains 99 tests. The new cases cover independently calculated paired
returns, Holm adjustments, circular block indices, quantile interpolation, positive/
negative/zero-mean synthetic cases, shared candidate resamples, sparse and degenerate
inputs, date alignment, configuration mismatch, seed reproducibility, global-RNG
isolation, Decimal isolation, plan registration and full artifact reproduction.

One test fixture intentionally alternates positive/negative values whose sums vanish
inside every even-length block. Its bootstrap is degenerate despite a nonconstant
original series; the program correctly withholds its p-value. Irregular synthetic
series exercise the ordinary calculation path separately.

These are algorithm and regression checks, not a comprehensive calibration study.
Before promoting any diagnostic into a research acceptance rule, simulate dependent
null and alternative processes, quantify false-positive rates and interval coverage
with Monte Carlo uncertainty, investigate block-length sensitivity, and compare an
independent implementation. Broader data and a comprehensive experiment history are
also needed. Adaptive-selector inference requires resampling/replaying the selection
procedure itself or another explicitly justified method.

Continuous paper-account replay, portfolio risk sizing, expanded data coverage and
scheduled state recovery remain separate milestones. No paid service, broker access
or additional runtime dependency was introduced.
