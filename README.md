# Research Desk — quantitative research and paper accounts (v0.6)

A local Python research platform with deterministic backtests, persistent $1,000
paper accounts, background jobs, a dashboard and reviewable Codex research requests.
No broker connection or live orders. Numerical work and saved-data audits run offline;
explicit data-fetch jobs and optional Codex CLI research use the network.
The bundled demo remains synthetic. A separately saved XLF snapshot exercises the
real-data pipeline; it is not a strategy recommendation or validated performance.

## Start the local dashboard

From this directory, with Python 3.11+ and the declared dependencies installed:

```powershell
python -m pip install -e .
python run.py demo --output demo-results
python run.py dashboard
```

Open **http://127.0.0.1:8765**. The dashboard starts empty in a fresh clone. It reads
saved reports and local SQLite state; create accounts and jobs using the CLI.
There is no bundled market-data redistribution, real-money balance or invented AI response.

On the original Windows workspace, `scripts/seed_demo.py` uses the locally retained
XLF snapshot to create cash and trend historical demonstrations. That snapshot is
intentionally excluded from Git. Each example account has separate simulated capital.

```powershell
./scripts/start.ps1   # hidden dashboard + Python worker; uses bundled Python if available
./scripts/stop.ps1
```

The display can be off, and normal computer use is unaffected. Sleep, shutdown or
logging out stops processing; restart the scripts to resume pending work. We do not
change power settings or install a Windows scheduled task. The worker coalesces missed
recurrences instead of replaying a burst of jobs after wake.

See [operations and commands](docs/operations-v6.md), [architecture](docs/architecture.md),
and [the contribution record](CONTRIBUTIONS.md). Code and tests are AI-assisted;
the record distinguishes the owner's requirements from Codex's implementation.

**Status:** functional local research prototype, not a validated trading system.
The current bootstrap calibration found inflated false positives with strong dependence.
No model response or statistical flag can enable live execution.

## Run from a checkout

Requires Python 3.11 or newer and `tzdata==2026.3` for reproducible time zones on
Windows (already available in this machine's bundled runtime). From this directory:

```powershell
python run.py demo
python -m unittest discover -s tests -v
```

Python is not currently on this machine's PATH. Use the bundled interpreter:

```powershell
& 'C:\Users\herog\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' run.py demo
& 'C:\Users\herog\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -m unittest discover -s tests -v
```

The CLI prints the path to a self-contained HTML report. Open it in any browser.
It needs neither a web server nor internet access. Jobs do not manipulate the UI.

For a checked ETF dataset:

```powershell
python run.py fetch --symbol XLF --start 2025-01-01 --end 2025-03-01 --output market-snapshots
python run.py audit-data --snapshot market-snapshots/09f488000e432b916068
python run.py backtest --snapshot market-snapshots/09f488000e432b916068 --output market-results
```

The example snapshot above is already saved. A new fetch produces a new snapshot ID
because the receipt includes its retrieval time. Use the path printed by `fetch`.
Start is inclusive and end is exclusive. The adapter currently admits USD stocks/ETFs on
NYSE/Arca, covers calendar years 2025–2026, and accepts ordinary dividends with a
sourced payment-date supplement. Vendor splits and capital-gain distributions remain
unsupported. Read `docs/data-policy.md` before
interpreting the results. Do not repeatedly search action-free windows for winners.

For an unchecked external file:

```powershell
python run.py backtest --csv your-bars.csv --symbol YOUR_SYMBOL --output var/runs
python run.py backtest --csv as-traded-bars.csv --symbol YOUR_SYMBOL --actions actions.json
```

CSV columns must be exactly `date,open,high,low,close,volume`. Each row is a completed
session with one consistent instrument, currency, session convention and adjustment
policy. Dates must increase strictly. Input is never silently sorted or repaired.
The generic CSV importer does not verify exchange sessions or corporate actions.
Its data is explicitly labeled unverified. The snapshot route performs the checks
above. Both routes remain engineering-only; no statistical significance is inferred.

## What exists

- Local read-only dashboard with searchable portfolios, ledgers, jobs, research and reports.
- SQLite paper-account revisions with immutable inputs and exact historical replay checks.
- ATR quantity caps and latched close-based loss/exposure controls for paper accounts.
- Durable job leases, bounded retries, pause/resume and recurring data/account updates.
- Audited research request export/import and optional ChatGPT-authenticated Codex CLI calls.
- Synthetic bootstrap calibration with false-positive and interval-coverage diagnostics.

- Immutable typed records for bars, decisions, fills and portfolio snapshots.
- A daily event loop with completed-close decisions and next-supplied-open fills.
- Whole-share, cash-funded, long-only entries; full-position exits.
- Configurable allocation, per-fill fees and adverse slippage.
- A stateful breakout/retest example with a five-bar holding-time exit.
- Same-allocation buy-and-hold and zero-interest cash baselines.
- SMA trend-cross and Bollinger re-entry swing hypotheses with explicit exit rules.
- Dividend entitlement, receivable and payment ledgers; unpaid cash cannot be spent.
- Explicit as-traded splits, with causal rebasing of history, shares and entry prices.
- Failures for fractional-lot split outcomes and unsupported corporate actions.
- Fixed chronological diagnostics: earlier bars warm indicators; evaluation starts flat.
- Candidate plans saved before simulation, including plans whose computation fails.
- Rolling training/test folds with a fixed selector, explicit gaps and cash fallback.
- Frozen per-fold selections saved before test computation.
- Cost sensitivity at 1×, 2× and 4× fees/slippage without reselecting on test results.
- Optional paired circular-block uncertainty estimates for the fixed strategy family.
- Holm correction across registered strategy/block-length comparisons, with sparse
  or degenerate cases withheld and retained in the family size.
- SHA-256 data/code identities, pinned run assumptions and source snapshots.
- A single immutable input read shared by parsing, computation, hashing and storage.
- Every strategy's implementation and execution configuration in the run identity.
- Exact cache-result comparisons and atomic artifact publication.
- Raw provider response, normalized CSV, retrieval receipt and revalidation command.
- Versioned exchange holidays, early closes, DST and missing-session checks.
- Human-readable HTML, candle chart, fill ledger, equity CSV and JSON artifacts.
- Unit and invariant tests, including future-data mutation and hand calculations.

No claim of profitability is made. The synthetic data exercises both a time exit
and a losing trade. It was constructed to exercise code, not selected as evidence.

## Design choices to understand

`dataclasses` make immutable contracts explicit. `Decimal` avoids binary-float money
surprises; transaction amounts and fees round to cents, half-up. Mark-to-market
equity retains precision and rounds only for display. The engine and indicators
use an explicit numerical context, isolated from the caller's rounding/trap settings.
`unittest` covers examples and invariants. We can add pandas/NumPy for larger feature matrices
and pytest/Hypothesis when that improves the workflow.

The entry allocation defaults to **20%**, an engineering placeholder, not a
personalized sizing recommendation. With whole shares and a $1,000 account, an
expensive instrument may be rejected. Fractional support will require explicit
broker-compatible lot and rounding rules. There is no leverage or shorting.

The only runtime dependency is pinned exactly in `pyproject.toml`: `tzdata==2026.3`.
Calendar conversion uses `zoneinfo`, with the pinned tzdata package explicitly loaded.
Each run records Python, code and every strategy configuration; snapshots record the
tzdata version and calendar hash. Source changes in a running process require a restart.
Installing is optional: `run.py` runs from the checkout. The test suite also builds
a wheel offline using setuptools/pip and runs its declared CLI outside the checkout.

## Source map

| File | Responsibility |
|---|---|
| `models.py` | Validated, immutable contracts |
| `data.py` | Strict CSV import |
| `actions.py` | Corporate-action contracts and validation |
| `calendar.py` | Bounded core-session schedule and coverage checks |
| `market_data.py` | Provider adapter, snapshot admission and revalidation |
| `engine.py` | Execution, cash and holdings |
| `strategies.py` | Indicators and close-only decisions |
| `evaluation.py` | Registered fixed-rule chronological comparisons |
| `walk_forward.py` | Rolling selection, fold isolation and cost sensitivity |
| `uncertainty.py` | Paired return sampling, exploratory bootstrap and Holm correction |
| `reporting.py` | Metrics, evidence storage and HTML |
| `storage.py` | Atomic publication and exact verification |
| `source.py` | Loaded source identity and change detection |
| `cli.py` | Offline application entry point |

## Run the new chronological comparison

The already-saved full-year XLF snapshot has 250 sessions and four ordinary dividends.
The source supplement and issuer workbook are local research inputs in `market-inputs/`.

```powershell
python run.py audit-data --snapshot market-snapshots/96a7da745819284a3fc8
python run.py evaluate --snapshot market-snapshots/96a7da745819284a3fc8 --split 2025-07-01 --output research-results-v3
```

`evaluate` records the three hypotheses and two baselines before computation, then
reports development and evaluation separately. It does not pick a winner or fit
parameters. `--lookback` and `--max-holding-bars` configure breakout/retest only;
trend and Bollinger settings are explicit `TechnicalConfig` defaults recorded in the
plan. Each strategy has its own simulated $1,000 account, not a shared portfolio.

The evaluation portfolio begins in cash on the split date. Earlier bars are available
for indicator calculations, but no earlier strategy decisions or holdings carry over.
The first possible evaluation fill is the next supplied session. A historical split
does not prove that a period was previously unseen by a human. Once inspected, it must
not be described as an untouched holdout. This is not walk-forward optimization or
multiple-testing correction. See [the milestone review](docs/milestone-v3.md).

To fetch a new dividend-containing window, first prepare a matching action document:

```powershell
python run.py fetch --symbol XLF --start 2025-01-01 --end 2026-01-01 --actions market-inputs/xlf-2025-actions.json --output market-snapshots
```

## Run walk-forward research

```powershell
python run.py walk-forward --snapshot market-snapshots/96a7da745819284a3fc8 --output research-results-v4
```

The default protocol uses 80 training sessions, a 5-session gap and up to 40 test
sessions per fold, after at least 21 indicator warm-up sessions. It requires at
least two test folds. A final partial fold with at least two sessions is included;
a one-session tail is explicitly reported as unused.

The three active candidates compete on **earlier training net marked return**.
Only positive returns with at least three completed training trades qualify; ties
use a stable name order. Otherwise the selector chooses cash. This small trade-count
filter is an engineering rule, not a statistical adequacy threshold. Buy-and-hold
is a reported comparator, not an eligible strategy. The selector never reads test
metrics. Every test also replays all candidates at the base, doubled and quadrupled
fee/slippage rates, preserving the original selected name.

Training and test accounts reset separately. Positions, orders and unpaid dividends
do not move between accounts. These are independent simulation runs, **not independent
statistical samples** and not a continuous trading-account return. Do not compound
fold returns. See [the v0.4 protocol and review](docs/walk-forward-v4.md) for limitations,
selection evidence, test coverage and the next implementation step.

## Optional uncertainty diagnostics

```powershell
python run.py walk-forward --snapshot market-snapshots/96a7da745819284a3fc8 --uncertainty --output research-results-v5
```

This option registers bootstrap settings before the simulations, saves paired daily
return differences, and adds `uncertainty.html`/`uncertainty.json`. It studies the
three fixed candidates versus same-allocation buy-and-hold at base costs. It does
not estimate significance for the adaptive selector. Block lengths 3, 5 and 10 are
all disclosed; no favorable block length is selected after seeing results.

Holm correction covers the nine candidate/block-length comparisons in this one
declared family. It does not correct prior human exploration or external trials.
P-values are withheld for sparse or degenerate cases. Intervals remain exploratory,
subject to dependence and stationarity assumptions. Read
[the v0.5 statistical contract](docs/uncertainty-v5.md) before interpreting them.

## Deliberate limits and further research

1. Broaden reviewed calendar/provider coverage and independently verify price
   adjustment conventions before making multi-year or multi-asset claims.
2. Paper accounts now replay continuously with one fixed strategy and risk wrapper.
   Shared-capital multi-asset allocation, strategy switching and cash-account settlement
   restrictions are not implemented.
3. A small synthetic calibration study is complete and exposes weak behavior under
   high persistence. Broaden experiment tracking beyond one declared family; extend robustness
   to parameter neighborhoods and market regimes without cherry-picking.
4. Expand independently sourced data and parameter/regime robustness before making
   any economic claim. Existing cost stresses and toy simulations are limited evidence.
5. Codex research uses explicit requests and manual review. CLI automation requires
   a separate ChatGPT sign-in; no paid API fallback or autonomous model-job loop exists.

For hands-on understanding and honest résumé ownership, start with
[the ownership lab](docs/ownership-lab.md) and [the contribution log](CONTRIBUTIONS.md).
No new paid service or runtime dependency was added in v0.3–v0.6.

Options, leveraged ETFs, real-time execution, live account access and distributed
agent swarms remain outside this prototype. See `docs/execution-semantics.md` for model
limits and `docs/review-followup.md` for the bugs fixed and their regression tests.
