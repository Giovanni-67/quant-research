# Working on Research Desk

Prioritize correctness, simple architecture, meaningful tests and honest evidence.
Read the relevant implementation and tests before changing behavior. Preserve existing
user changes. Never weaken an admission rule or test to make a result look better.

## Structure and invariants

- Python standard library plus pinned tzdata; avoid unnecessary dependencies.
- `run.py` runs the checkout; `quant_research.cli:main` is the installed entry point.
- Decimal and the explicit numeric context own accounting. LLMs only supply untrusted
  research text; never execute a model suggestion, broker order or risk override.
- Signals use completed closes and fill at the next supplied open. Preserve causal
  history, corporate-action treatment and source/data identities.
- The dashboard is loopback-only and read-only. Keep SQL parameterized and render model
  text with text nodes. No secrets, account credentials or private data in reports.
- Paper ledgers and evidence directories are user records. Do not delete or rewrite
  them during tests, upgrades or demonstrations. Tests use temporary state.
- Source changes invalidate running numerical processes and existing account advancement.
  Restart processes; preserve old ledgers and require a separately reviewed new account.

## Verification

Run focused tests while developing, then `python -m unittest discover -s tests -v`.
The suite includes a real wheel build and execution from an isolated installed layout.
Use the bundled Python path documented in README if Python is not on PATH.
Check relevant normal, boundary, malformed, duplicate, failure and concurrency cases.
Add regression tests for reproduced bugs. Browser-test affected interface behavior.
Do not claim a test passed without observing it. Explain external blockers precisely.

## Public development record

Review diffs and excluded files before committing. Make coherent commits and push
tested work to the existing `origin` regularly; the owner has authorized normal pushes.
Never force-push, rewrite published history, change repository permissions, add
collaborators or merge outsiders' pull requests without explicit authorization.
Keep downloaded data, local ledgers, credentials and generated artifacts out of Git.
Keep README and CONTRIBUTIONS truthful, including AI assistance and unverified claims.
Do not fabricate earlier commits or credit the owner with work they have not done.

Final updates should state what changed, verification performed, important edge cases,
whether checks passed, and any untested behavior or remaining limitation.
