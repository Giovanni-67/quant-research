# Execution and research contract — version 3

## Session order

For each supplied bar:
1. Apply an explicit split or establish dividend entitlement from pre-open holdings.
2. Move payable receivables to cash at the first supplied session after the payable date.
3. Execute the previous close's pending decision at this open with adverse slippage.
4. Deduct/credit rounded notional and fee. Update cash and quantities.
5. Mark equity to cash + shares × close + outstanding dividend receivables.
6. Call the strategy with only the prefix through that completed bar.
7. Store a new decision for the next supplied session.

The close on session t cannot fill at t's close. A gap from t's close to t+1's open
is not earned by a new entrant. A previously held position remains exposed to gaps.
Strategies are trusted, reviewed Python code: a history prefix prevents accidental
future access through this interface, but is not a sandbox against malicious code.
Fresh instances are required per run because setup detection is stateful.

## Cash and execution

Initial balance is USD 1,000. BUY requires flat holdings; SELL exits all units.
BUY budget is cash times the entry allocation. Fee/slippage are included in that
budget and whole-share quantity rounds down. No cash borrowing is permitted.
Appreciation can take exposure above the entry allocation; automatic rebalancing
and a separate ongoing exposure ceiling are future work, not implemented controls.

Slippage adjusts the fill price against the trade direction. Fees are basis points
of each rounded fill notional. Both entry and exit pay fees. Synthetic friction can
place a fill outside the OHLC range: it is a stress assumption, not an observed quote.
Zero-volume bars reject the dataset before simulation; a day's total volume cannot
decide an opening fill. Other order rejections cancel the order rather than silently
carrying it forward. A final decision remains pending; an open holding is
marked, not forcibly liquidated. Cash interest, taxes and financing are
not included. Defaults are illustrative, not Robinhood pricing.

## Breakout/retest

- Resistance is the maximum high of the previous 20 completed bars, excluding the
  current decision bar.
- A close more than 0.5% above resistance starts a setup and freezes that level.
- On one of the next 3 bars, a low within +/-1% of the level and a close at/above it
  confirms a retest. Confirmation schedules an entry, not an immediate fill.
- A close more than 1% below the level invalidates the setup. A setup also expires
  after 3 bars. Breakout and retest cannot occur on the same bar.
- While held, exit signals occur on a close 5% below entry fill, a close 10% above
  entry fill, or the fifth completed holding bar. They execute next supplied open.
- The entry session counts as holding bar 1. Five holding bars typically span about
  a week; holidays and missing data can alter elapsed time.

Stops here are **close-based signals**, not broker stop orders, guaranteed loss
limits, or intraday fills. This avoids assuming intrabar event order from OHLC bars.
Gap risk is represented by the next open and can exceed the threshold substantially.
Parameters are examples, not optimized or validated defaults.

## Dividends and splits

An ordinary dividend is owed to the quantity held before the ex-date open. Selling
at that open retains the entitlement; buying then creates none. The account-level
entitlement is rounded to cents half-up once. It raises receivables, not cash. It
remains owed after a sale, and remains in equity if the simulation ends before
payment. There is no automatic reinvestment. Taxes and broker-specific adjustments
to rounding are not represented. Making cash available only at the first session
after the payable date is a conservative daily-model convention, not a claim about
the exact time a broker credits a dividend.

On an as-traded split's effective session, quantity multiplies by the ratio and the
entry-price reference divides by it. Previously observed OHLC divides by the ratio,
and volume multiplies, only from that effective session onward. Stateful strategies
must implement `on_split`: breakout/retest rebases its frozen level. Existing ledger
records are not rewritten. Pending decisions contain BUY/SELL intent, not stale
fixed quantities; execution computes new entry units or sells the updated holding.
Fractional-lot outcomes fail rather than inventing a cash-in-lieu payment.

Ordinary dividends do not rebase technical price history or entry-price stops. An
ex-dividend price drop can trigger a price-based signal; the ledger still includes
the dividend entitlement. Total-return indicators would be a separate hypothesis.

## Other fixed hypotheses and chronological evaluation

Trend swing enters when the 5-close SMA crosses above the 20-close SMA. Bollinger
swing enters when the previous close was below its lower band and the current close
returns inside/above the current lower band. Bands use a 20-close population standard
deviation and width 2; the current close is included only after that close is known.
Trend exits on a fast/slow reversal; Bollinger exits at/above its mean. Both also use
the same default 5% close-based stop, 10% close-based profit exit and five holding-bar
limit. Priority is stop, profit, holding limit, then family-specific exit.

`evaluate` registers all candidate specifications, data/action/source identities and
the boundary before any simulation. It runs development separately, then initializes
fresh strategies and fresh cash for evaluation. Warm-up bars supply historical prices
without decisions, positions or orders. No fitted parameters or state carry over.
The evaluation-date close is the first eligible decision. Minimum warm-up is 21 bars
or breakout lookback + 1, whichever is larger; at least 20 evaluation sessions are
required to catch accidental tiny windows. These minima do not establish adequate
statistical sample size. There is no random split and no automatic winner selection.

This registry covers `evaluate` invocations; standalone `backtest`, external notebooks,
human experiments and deleted files are not a comprehensive global trial history.
It is an audit aid, not multiple-hypothesis-testing correction or proof of a pristine
holdout. Future walk-forward work must explicitly define fit windows, selection rules,
overlap/purge rules, portfolio transitions and dependence-aware inference.

## Evidence and scope

Total return uses ending marked equity / starting cash - 1. Drawdown peaks include
initial capital. Fees, cash and quantities remain visible in the ledger. No Sharpe,
p-values, win probability or annualized claims are produced by this tiny demo.
Buy-and-hold has the same allocation and first-close/next-open convention, which
helps isolate timing but is not a fully invested market benchmark.

Runs are content-addressed by one frozen input payload, source, interpreter version,
every strategy specification/configuration, symbol and provenance. Reuse compares the
newly computed artifacts byte-for-byte, not just saved checksums. Different CSV byte
formatting produces a different ID intentionally. Hashes are not signatures. Publication
is atomic on the local filesystem; failures during staging do not publish a partial
bundle. This is not a durable multi-worker queue, distributed transaction, or guarantee
of power-loss durability. Source edits in a running process require a restart.

The checked snapshot route verifies the 2025–2026 exchange calendar, requested coverage
and reported events against the applicable admission policy. It preserves vendor OHLC without applying
adjusted-close scaling. The raw CSV route remains unverified. See data-policy.md for
provider limitations and the corporate-action contract. Neither route establishes
statistical validity. Historical universe selection, certified OOS studies, multiple-testing and
paper persistence remain later milestones. No broker connection exists.
