# Validation record — September 10, 2026

## Automated checks

Command: `python -m unittest discover -s tests -q`

Result: **42 tests passed**, including an actual offline wheel build and execution
of the packaged CLI from an isolated installed layout. Python: 3.12.14.

The three original review defects have dedicated regression coverage. Additional
tests cover fixed Decimal settings, immutable bar/result linkage, code identity,
atomic publication, holiday/session coverage and raw-response admission rules.

## Integration checks

- Downloaded XLF daily data for 2025-01-01 through 2025-03-01 exclusive.
- Admitted 39 sessions; no reported actions in that requested window.
- Reopened the snapshot in an ordinary sandbox worker after fixing workspace ACL
  inheritance in the publisher.
- Reparsed and revalidated the saved raw response offline using `audit-data`.
- Ran the unchanged breakout/retest parameters and both baselines.
- Repeated the run and confirmed the existing evidence bundle matched all newly
  computed artifact bytes.
- Requested XLF through 2025-04-01 exclusive as a separate negative test. The
  corporate-action gate correctly rejected the distribution-containing window.
- Generated an updated synthetic demo and real-data engineering report.

## Interpretation

These checks establish the tested software behavior, not investment suitability,
profitability or production readiness. The short market sample exercises ingestion
and accounting. It is not an out-of-sample test and was not used to optimize rules.

No live orders, account access, paid services or scheduled recurring jobs were
created. Full corporate-action accounting and statistical validation remain future
milestones. The data-policy document states the bounded calendar and vendor caveats.
