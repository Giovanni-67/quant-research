# Walk-forward protocol and review — v0.4, 2026-09-10

This milestone implements rolling historical strategy selection and cost sensitivity.
It does not certify a profitable strategy, complete statistical validation or
continuous live-account behavior.

## The protocol, before interpreting results

The defaults are deliberately small and explicit. No strategy parameters or
eligibility thresholds were changed after inspecting the real-data fold outcomes.

1. Keep three fixed active hypotheses: breakout/retest, SMA trend swing and Bollinger
   re-entry. Buy-and-hold and cash are displayed as comparators. Cash is also the fallback.
2. Reserve at least 21 earlier bars for price-based indicator warm-up (or breakout
   lookback + 1, whichever is larger). Each rolling training decision window spans
   80 sessions. Its fresh account begins with $1,000 and the existing cost/allocation rules.
3. Leave five supplied sessions between the training window and test window.
   Training scores contain no returns from that gap or later dates. The later test
   strategy can observe completed gap prices when computing its indicators.
4. Rank only candidates with positive training net marked return and at least
   three completed round trips. Select highest net return; exact ties use ascending
   candidate name. If none qualifies, select cash. Three trades are plainly too few
   to establish an edge; the count is a guard against ranking zero/one-trade examples,
   not a statistically derived eligibility rule.
5. Persist the choice before any test computation. Test it on the next 40 sessions,
   starting a fresh account and strategy. Test decision one is at the first test
   close; the earliest fill is at the following supplied open.
6. Advance by the test-window length and repeat with a rolling 80-session training
   window. Previous test dates may become later training data, which is chronologically
   legitimate. Test windows never overlap. Keep a final partial window of at least
   two sessions; explicitly report a one-session tail as unused. Require at least
   two folds so a single split is not called a walk-forward study.
7. Replay every candidate on each test window with fee and slippage basis points
   multiplied by 1, 2 and 4. Preserve the original selected candidate at every cost
   level; stress results never feed back into selection. Initial cash and allocation
   stay the same. Changed costs can change whole-share quantities or future signals,
   so returns need not move monotonically across these complete replays.

Training score is ending marked equity divided by initial cash, minus one. It includes
incurred fees and dividend entitlements; an open position is not hypothetically sold
for scoring. That choice can favor terminal open positions and must be considered
when interpreting rankings. There is no drawdown limit in the selector yet.

Chronological training/test separation and an explicit gap follow the general pattern
described in [scikit-learn's TimeSeriesSplit documentation](https://scikit-learn.org/stable/modules/generated/sklearn.model_selection.TimeSeriesSplit.html).
This implementation uses small Python dataclasses and the existing engine, without
adding scikit-learn. Its gap is **not** a general solution for overlapping prediction
labels, purging or embargo. Those require an explicit future-label definition that
this rule-based prototype does not have.

## How the code enforces the boundary

`folds_for` creates immutable index boundaries. `prefix_dataset` constructs input
containing only bars and effective corporate actions through the training end.
`_window_results` passes that truncated input to fresh strategy instances and enables
decisions only inside the training window.

`TrainingScore` holds just candidate name, finite net return and completed trade
count. `select_candidate` is a deterministic pure function of those scores and the
registered minimum. It receives no bars, test results or file paths. The code that
loads/runs test windows is executed only after selection is saved. This separation
is reviewable; tests also intercept calls and inspect the actual data lengths.

The parent plan fingerprints the full research input, but that hash is provenance,
not a selector feature. Mutating future input changes the plan/run identity while
preserving prior numerical choices and ledgers. Registry hashes are not signatures
and do not prevent a researcher from deleting experiments or conducting external
trials. They are a local audit trail, not a complete multiple-testing control.

## Account boundaries and what the report does not aggregate

Each training, test and cost scenario is its own account. Historical prices warm
indicators, but prior positions, decisions and receivables do not carry over. At the
end of a fold, existing holdings and unpaid dividends remain marked in that fold.
There is no invented boundary sale or transfer of marked equity to the next fold.

Consequently, the report does not multiply fold returns, sum dollar profits into one
account, calculate a cross-fold drawdown or claim a continuous portfolio track record.
Shared training data, market dependence and strategy selection also mean fold
outcomes are not independent statistical observations. No p-value or confidence
interval is produced. Cost scenarios are not independent confirmations.

## Real-data run

Input is the existing 250-session XLF snapshot `96a7da745819284a3fc8`, with four
issuer-reconciled dividends. This history has already been inspected in prior
milestones, so these are historical diagnostics, not a pristine holdout study.

Comparison ID: `64b4761bef00f805da72`.

| Fold | Training decisions | Test decisions | Test sessions | Selected |
|---|---|---|---:|---|
| 1 | Feb 4–May 29, 2025 | Jun 6–Aug 4, 2025 | 40 | Cash |
| 2 | Apr 2–Jul 28, 2025 | Aug 5–Sep 30, 2025 | 40 | Cash |
| 3 | May 30–Sep 23, 2025 | Oct 1–Nov 25, 2025 | 40 | Cash |
| 4 | Jul 29–Nov 18, 2025 | Nov 26–Dec 31, 2025 | 24 | Cash |

All four selections fell back to cash. In fold 1, Bollinger met the three-trade
minimum but lost money in training; the other candidates had too few closed trades.
In the other folds, none met both eligibility conditions. Selected accounts therefore
stayed at $1,000 under all three cost scenarios, with zero interest assumed.

This outcome does not demonstrate that the cash policy is optimal or statistically
superior. It shows that the specified selector abstained under sparse evidence.
Changing the threshold after seeing these results would be a new experiment, not
confirmation of the original one. The report displays every rejected candidate's
later results as well, with no retroactive replacement of the selected candidate.

[Open the comparison](../research-results-v4/comparisons/64b4761bef00f805da72/report.html).

## Artifacts and verification

- `plans/<id>/plan.json`: registered data/code identities, candidate specifications,
  fold boundaries, costs and protocol before simulation begins.
- `selections/<id>/selection.json`: training scores and selected name saved before
  test metrics are computed. A test failure leaves this evidence in place.
- `runs/<id>/`: separate training/scenario reports, complete result objects,
  trade/equity/corporate-action ledgers and source/input snapshots.
- `comparisons/<id>/`: plan, fold records, descriptive counts, all-candidate metric
  CSV and an HTML report with expandable training/selection/test detail.

All **85 tests passed** (68 prior tests plus 17 new tests). New tests cover rolling
indices, gaps, partial/singleton tails, invalid protocols, cash fallback, exact ties,
minimum-trade eligibility, immutable experiment identity, pre-test choice persistence,
the actual truncated inputs sent to each engine, fixed selection across cost scenarios,
active-candidate execution, Decimal-context isolation and deterministic reruns.

Future-price mutation cannot alter earlier training choices. Later-fold mutation
cannot alter the first fold's complete test result objects. Future corporate-action
amount changes cannot alter earlier training scores. Unpaid training dividends do
not leak into test cash; test-period entitlements still get paid correctly.

The package installation/demo test remains in the suite. The real-data CLI also
completed, and local report links were checked. These checks support the covered
behavior; they do not prove there are no remaining bugs or certify source data.

## What remains and what to build next

The main limits are still single-vendor/single-asset evidence, bounded 2025–2026
calendars, limited corporate-action coverage, sparse trading samples and no formal
multiple-testing/dependence-aware inference. The historical selector is not a
paper-account service. No broker account, paid service or new runtime dependency
was added.

The next validation increment should define a benchmark-relative return series and
the unit of inference, then implement dependence-aware uncertainty on a fixed
experiment family. Preserve all trials and test null/degenerate/small-sample cases
before exposing any significance result. Do not attach an ordinary independent-trade
t-test to these selected, dependent observations.

Continuous portfolio replay needs a separate contract for switching strategies while
positions are open, liquidation costs, remaining dividend claims and settlement. It
must reconcile against the current engine before persistent paper state and scheduled
jobs are enabled. The owner's ATR exercise remains available as a concrete personal
contribution; it was not silently completed by Codex.
