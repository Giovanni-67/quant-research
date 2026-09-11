# Operating Research Desk

All commands run from the repository root. Use `python run.py --help` for the complete
command list. On the original Windows machine, the bundled Python path is recorded in
the README; the start/stop scripts discover it automatically. No paid service is required.

## Paper accounts

```powershell
python run.py paper-create --name my-paper --snapshot PATH_TO_CHECKED_SNAPSHOT --strategy trend_swing
python run.py paper-update --name my-paper --snapshot PATH_TO_EXTENDED_SNAPSHOT
python run.py paper-list --name my-paper
python run.py paper-pause --name my-paper
python run.py paper-resume --name my-paper
```

Creation defaults to forward paper: the snapshot must reach the latest completed
exchange session. Earlier bars warm indicators; account decisions start at its last
bar. No historical profits are credited on creation. `--historical` explicitly enables
replay demonstrations instead. The dashboard distinguishes historical accounts.

Each account starts with its own simulated $1,000, 20% entry allocation cap and whole
units. Defaults include 5 bps fees and 5 bps adverse slippage, a 25% close exposure
ceiling, 10% maximum drawdown latch, 3% daily loss latch and an ATR sizing budget of
1% of equity divided by twice 14-session Wilder ATR. These are engineering defaults,
not tuned or statistically validated risk choices. ATR scales quantity; it does not
guarantee a loss limit or create an intraday stop. An exposure breach requests a full
exit at the next supplied open. A loss latch remains halted on subsequent updates.

Pausing stops account updates; it does not liquidate holdings. Resuming does not clear
a risk latch. Updates preserve all earlier bars and effective corporate actions, then
replay from the original start and compare prior fills, balances, signals, rejections
and action records. Changed history fails without overwriting the ledger. Duplicate
inputs return the existing revision. This is deliberately conservative and may reject
legitimate vendor revisions, which require explicit investigation.

Python source changes also stop advancement. Keep the original ledger and create a
new reviewed account; do not edit hashes to bypass the check. Account computation uses
a SQLite transaction, so a crash cannot publish a partial revision. Replaying full
history is simple and auditable, but not optimized for large intraday workloads.

## Jobs and background processes

Create a JSON payload and submit it explicitly:

```json
{"snapshot":"market-snapshots/YOUR_ID"}
```

```powershell
python run.py job-add --kind audit --payload audit-job.json --interval 86400
python run.py worker --once
python run.py worker
python run.py job-list
python run.py job-pause --id JOB_ID
python run.py job-resume --id JOB_ID
```

Supported payloads:

| Kind | Required keys | Optional keys |
|---|---|---|
| `audit` | `snapshot` | — |
| `walk_forward` | `snapshot`, `output` | `uncertainty` boolean |
| `paper_update` | `snapshot`, `portfolio` | — |
| `fetch` | `symbol`, `start`, `end`, `output` | `actions` file |
| `refresh_paper` | `portfolio`, `output` | `actions` file |

Paths freeze as absolute at submission. `fetch` uses explicit inclusive start and
exclusive end. `refresh_paper` retrieves full account history through the latest
completed session, checks admission, then advances an active forward account. It skips
already current accounts. Dividend supplements must remain complete and sourced; the
job fails rather than inventing missing payment dates. Historical accounts cannot be
silently changed into forward accounts. Repeating `paper_update` with a fixed snapshot
only rechecks that snapshot; use `refresh_paper` for new market data.

Workers claim a ten-minute lease, retry up to three attempts and reject completion
from stale lease holders. Missed recurrences coalesce to one run; jobs are at-least-once,
not exactly-once. Immutable publications and paper idempotence protect replayed work.
Long computations exceeding a lease can be duplicated, so run one worker for this
prototype. Pausing an in-flight job does not forcibly cancel its already started work.

`scripts/start.ps1` starts dashboard and worker hidden, requesting below-normal process
priority. `scripts/stop.ps1` verifies recorded PID, executable and process start time
before stopping them. Logs and PID records live in `var/`. The display may be off;
the computer must remain awake. There is no automatic restart after logout/reboot and
no Windows Task Scheduler registration. Run the start script again after restart.

## Codex research without paid API services

```powershell
python run.py research-submit --role critique --question "Review the assumptions" --evidence evidence.json
python run.py research-export --id REQUEST_ID --output var/research/REQUEST_ID
python run.py research-import --id REQUEST_ID --response response.json
```

Use the exported `prompt.txt` and `schema.json` in your existing ChatGPT/Codex session.
The response contains `summary`, `hypotheses`, `concerns`, and `suggested_experiments`.
It is stored as untrusted text requiring review. HTML is rendered as text, never code.
Duplicate identical responses are accepted; a different response cannot overwrite a
completed request. Submit a new request with revised context instead.

For explicit CLI execution, put the Codex executable on PATH, authenticate it using
your ChatGPT account, then run:

```powershell
codex login
python run.py research-run --id REQUEST_ID --output var/research/REQUEST_ID
```

The wrapper checks `codex login status`, removes API-key environment variables, ignores
user CLI configuration and requests a read-only sandbox. It never falls back to a paid
API key. Read-only sandboxing does not guarantee filesystem-read isolation; export only
appropriate evidence and do not put credentials in request directories. Output schema
validation does not establish factual accuracy. No model text is executed as a job,
calculation, risk change or trading instruction.

During verification, this machine's CLI reported **Not logged in**. The subscription
guard correctly refused execution. A critique authored in the current Codex session was
imported through the manual path and labeled accordingly. Successful automatic CLI
inference remains unverified until that CLI is signed in. This does not prevent local
Python jobs or manual research review. See official [authentication](https://developers.openai.com/codex/auth)
and [noninteractive usage](https://developers.openai.com/codex/noninteractive) documentation.

## Validation status

The suite has 121 tests, including the installed wheel entry point and packaged
dashboard resources. New checks cover ATR hand calculations, warm-up signal preservation,
split-adjusted order caps, receivables in risk equity, halted-state persistence, transaction
rollback, duplicate updates, revised bars/actions, stale data, source changes, lease expiry,
stale worker completion, bounded retry, recurrence coalescing, response immutability, and
loopback HTTP host/path/method restrictions, simultaneous account/worker claims, and
completed-session refresh boundaries. Browser interaction and launcher restart
checks supplement the automated suite. A real-data trend account was advanced from a
120-session prefix to the full saved 250-session input without altering prior history.

`python run.py calibrate --trials 40 --repetitions 199` exercised six Gaussian AR(1)
null/alternative cases. Under the null, family flags occurred in 2/40 independent,
2/40 moderately persistent and 9/40 strongly persistent trials. The last case exposes
inflated false positives; the report also saves Wilson Monte Carlo intervals and
marginal coverage. Forty trials per case provide limited precision, and the synthetic
process is not a market model. Holm adjustment cannot repair invalid input p-values.

The data adapter is unofficial, single-vendor and restricted to NYSE/Arca USD stocks
and ETFs in 2025–2026. Nasdaq, multi-year coverage, delisted-universe survivorship control,
independent price verification, shared-capital allocation, settlement restrictions,
automatic parameter/regime robustness, adaptive-selector inference, options and live
execution remain unsupported. A working research platform does not imply a profitable
strategy or that all future research work is finished.

## Backups

Stop both processes, then copy `var/app.sqlite` plus any existing `-wal` and `-shm`
sidecars and the evidence directories to your backup location. Keep snapshots and
source-bound reports with the ledger. Do not copy only an actively written SQLite
main file; use a consistent SQLite backup operation if online backups are later added.
Local state and downloaded data are excluded from GitHub.
