# v0.3 review and evidence — 2026-09-10

The corporate-action accounting milestone and the first chronological research
diagnostic are implemented. This is a tested research prototype, not a completed
trading platform or validated profitable strategy.

## What changed and why

The old importer rejected every dividend-containing window. The new path requires
an explicit ordinary-dividend supplement, checks its ex-dates and amounts against
the vendor, and records payable dates and sources. For XLF, the issuer's six-decimal
amounts reconcile with the vendor's three-decimal rounding. There is no arbitrary
tolerance or silent replacement: the receipt preserves the reconciliation.

The engine separates cash from dividend receivables. This prevents early dividend
reinvestment and preserves an entitlement when a position is sold on the ex-date.
Explicit as-traded splits adjust shares, entry-price references, historical indicator
inputs and frozen breakout levels together. Previously recorded decisions remain
unchanged. Unsupported fractional-lot and vendor-adjustment cases fail admission.

New trend-cross and Bollinger re-entry hypotheses share the deterministic execution
engine. Chronological evaluation registers every candidate before running, starts
evaluation with fresh cash/state, and uses earlier prices only as indicator history.
It reports every candidate without selecting a winner or asserting significance.

The strategy specification is now captured before decisions can mutate state.
Corporate-action input identity and the evaluation start date participate in run
identity, preventing a cached result from being reused under different assumptions.

## Verification

All **68 automated tests passed** using Python 3.12.14 and tzdata 2026.3, including
the offline built-wheel/installed-entry-point test. The prior version had 42 tests.

New verification covers independent cash/equity examples, ex-date purchase/sale
eligibility, unpaid entitlements, payable-date timing, split conservation and technical
level continuity, reverse-split rejection, future-data mutation, mismatch/tamper
rejection, chronological boundaries, indicator warm-up, both new strategy signals,
registration before a simulated failure and reproducible comparisons.

The full-year snapshot was reparsed offline and admitted with 250 sessions and four
dividends. Repeating the chronological CLI run returned the same comparison and run
IDs, with exact artifact comparison. The older 39-session snapshot still passes its
original no-reported-actions admission contract. The packaged synthetic demo runs.

This verification supports the tested behavior. It does not certify the absence of
all bugs, source-data completeness or future investment performance.

## Fixed historical comparison

Snapshot: `96a7da745819284a3fc8` (XLF, 2025-01-01 through 2026-01-01 exclusive).
Comparison: `2ecd982a2ad024a38cc5`.
Development: 122 sessions, January 2–June 30, run `b0b85805c6fb8d1beee3`.
Evaluation: 128 sessions, July 1–December 31, run `89bba3d7c7149254291e`.

Each strategy has a separate $1,000 account, 20% entry allocation, whole shares,
5 basis points of adverse slippage and 5 basis points of per-fill fees. These are
engineering assumptions. Results include ordinary dividends and terminal marks;
there is no forced sale at a period boundary.

| Candidate | Development return | Evaluation return | Evaluation completed round trips |
|---|---:|---:|---:|
| Breakout/retest | +0.760% | +0.238% | 1 |
| Trend swing | +0.272% | −0.120% | 3 |
| Bollinger swing | −0.198% | +0.159% | 3 |
| Same-allocation buy-and-hold | +1.673% | +0.700% | 0; position stays open |
| Cash | 0% | 0% | 0 |

The sample contains too few active-strategy trades to support an edge. The periods
have unequal length and fresh portfolio state; these percentages are neither
annualized nor a stitched continuous strategy return. This asset is a sector ETF,
not a representative stock universe. No parameter was changed to improve these
observed returns. Historical data already inspected cannot serve as an untouched
future holdout.

[Open the local comparison](../research-results-v3/comparisons/2ecd982a2ad024a38cc5/report.html).
The report links separate period reports. All strategies' fills, daily equity and
corporate-action ledgers are in CSV/JSON. `actions.json` preserves the exact optional
input bytes; an empty file denotes no supplied actions and is accepted by the loader.

## What remains and the next implementation

1. **Data breadth:** reviewed calendars cover only 2025–2026; the checked feed admits
   NYSE/Arca USD ETFs. Equities, older calendars, delistings, point-in-time universe
   membership and independent OHLC reconciliation remain open. Vendor split windows
   are blocked until price adjustment conventions can be verified. Cash-in-lieu,
   simultaneous events, due bills, spin-offs and capital gains remain unsupported.
2. **Statistical validation:** the next research-engine task is to define a fixed
   experiment family and implement repeated chronological folds with a selector
   that cannot read later data. Tests must mutate later folds and prove earlier
   choices unchanged. Explicitly decide whether positions reset or carry across
   folds, and how holding-period overlap is handled, before reporting aggregate
   results. Add uncertainty and multiple-testing controls after that protocol is
   defined; a registry alone is not a correction.
3. **Risk and operations:** add ATR-informed sizing and portfolio-wide exposure
   accounting after the owner's indicator lab, then persistent paper state with
   replay/idempotency/recovery tests. Only then wire scheduled background jobs and
   monitoring. Current runs do not connect to accounts or place live orders.
4. **Research interface:** the HTML reports work offline, but a queryable experiment
   dashboard and bounded Codex research tools remain later work. LLMs will consume
   deterministic results; they will not calculate returns or approve statistical claims.

These are real remaining engineering tasks, not features hidden behind configuration.
This milestone added no paid service and no runtime dependency.

## What to learn from this milestone

- State machines and event ordering: ownership before an ex-date open differs from
  holdings after that open; entitlement differs from spendable cash.
- Data contracts: a source discrepancy should be recorded and reconciled under an
  explicit rule instead of silently repaired.
- Causal feature generation: splits can change current share units without changing
  the decisions recorded before the split.
- Experiment design: a chronological boundary prevents one class of leakage but
  does not solve repeated testing, selection bias or human exposure to a holdout.
- Reproducibility: source, data, corporate actions and execution assumptions all
  need to be bound to an immutable evidence bundle.
