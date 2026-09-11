# Stock/ETF data admission — version 3

Version 3 additionally admits vendor metadata type EQUITY on the same reviewed
NYSE/Arca USD session contract. ETF snapshots retain their original provenance.
This does not add Nasdaq, delisted-universe coverage or independent vendor verification.

This is a software-engineering check, not certification that a strategy works.

## Why these libraries

`urllib.request` fetches one bounded public JSON response with a timeout and size
limit. `Decimal` parses price numbers without introducing another float conversion.
`zoneinfo` converts exchange-local sessions to UTC; the exact `tzdata==2026.3` package
provides the time-zone rules on Windows and other platforms consistently.
`importlib.resources` loads packaged fixtures/calendar data after installation.
No pandas, broker SDK, cloud database or paid feed is needed for this milestone.

## Calendar

The source-controlled calendar covers 2025 and 2026 ONLY. It checks all expected
sessions between the requested inclusive start and exclusive end, including missing
first/last sessions. It rejects extra dates, duplicates, weekends and exchange
closures. It knows early closes and UTC offset changes but not individual-security
halts. NYSE Arca shares the listed holiday/core-session schedule.

Sources consulted:
- [NYSE 2025 trading calendar](https://www.nyse.com/publicdocs/ICE_NYSE_2025_Yearly_Trading_Calendar.pdf)
- [January 9, 2025 closure notice](https://www.nyse.com/publicdocs/nyse/markets/american-options/rule-interpretations/2025/National_Day_of_Mourning_20250102.pdf)
- [NYSE holidays and core hours](https://www.nyse.com/trade/hours-calendars)

Coverage is bounded deliberately. A future calendar release must be reviewed and
versioned; the program never extrapolates exchange holidays indefinitely.

## Snapshot contract

`fetch` requests Yahoo's public chart endpoint, daily quote OHLCV, and dividend,
split and capital-gain events. It stores accepted raw bytes plus a normalized CSV.
The normalized data retains provider numeric values; it does not apply adjusted-close
ratios or silently repair missing prices. A receipt includes the exact request,
retrieval time, payload hash, normalization hash, time-zone version, calendar hash,
instrument metadata and admission results.

`audit-data` verifies the artifact set/hashes, reparses the original response,
rechecks the current calendar and policy, and compares normalized bytes. `backtest
--snapshot` performs the same validation before computation. The generic `--csv`
route remains explicitly unverified and cannot claim these checks passed.

The provider must identify the instrument as a USD ETF listed on NYSE/Arca with
America/New_York timestamps and daily granularity. The adapter refuses null/misaligned
arrays, invalid prices, zero volume, duplicate dates, incomplete coverage and
incomplete sessions. Missing data is not imputed. A zero-volume day fails the dataset
before any trading simulation; full-day volume never determines an opening fill.

## Corporate actions: reconcile explicit events

Without a supplement, `reject_reported_corporate_actions_v1` still refuses reported
events. With `--actions`, `explicit_ordinary_dividends_v1` requires every vendor
ex-date to match exactly one supplied ordinary dividend and its payable date.
Missing/extra events fail admission. Reported amounts must match exactly or match
the supplied amount rounded half-up to 0.001 dollars when the vendor amount is at
that precision. This explicit rule handles the observed XLF feed rounding. The
receipt records both amounts and the reconciliation method; the ledger uses the
supplement's precise amount. A disagreement outside that rule fails admission.

The source reference is required but is not automatically authenticated. For the
saved 2025 XLF run, the amounts and payable dates were extracted from the issuer's
[historical distributions workbook](https://www.ssga.com/library-content/products/fund-data/etfs/us/spdr-etf-historical-distributions.xlsx),
linked by its [distribution page](https://www.ssga.com/us/en/individual/resources/documents/etf-dividend-distributions).
The locally saved workbook hash is included in each source reference. Its columns
explicitly identify ex-date, record date, payable date, dividend and capital gains;
the four selected XLF rows have no nonzero capital gains. Payment-date authentication
for a different user-supplied supplement remains the researcher's responsibility.

Vendor split windows, capital-gain distributions and unknown categories still fail.
The generic CSV route supports explicit share splits only under an `as_traded`
price-basis declaration. The declaration is a contract, not an independent audit.
Absence of a provider event is not independent proof that no action occurred.

The engine now calculates entitlements, receivables, conservative payment availability,
and as-traded split changes to holdings, entry-price references and active technical
levels. It does not calculate:
- Cash in lieu of fractional shares or reinvestment.
- Historical corrections, spin-offs or special distributions.

Simply multiplying by adjusted-close ratios and treating the output as historical
executable prices would obscure both cash accounting and historical share quantities.

Vendor quote OHLC may already reflect retrospective split scaling. No independent
claim of raw exchange prices or point-in-time data is made. Even accepted snapshots
remain `vendor_checked_engineering_only`. Data agreement across sources and action
reconciliation beyond ordinary cash dividends are further work.

Action files use decimal strings, increasing dates and one event per session:

```json
{
  "schema_version": 1,
  "symbol": "EXAMPLE",
  "price_basis": "as_traded",
  "events": [
    {"type": "dividend", "ex_date": "2025-03-24", "pay_date": "2025-03-26", "amount": "0.50", "source": "synthetic example"},
    {"type": "split", "effective_date": "2025-06-02", "ratio": "2", "source": "synthetic example"}
  ]
}
```

The example is synthetic. Every effective date must appear in the supplied bars;
a payable date can lie after the last bar. A ratio of 2 means two new shares for one
old share. Simultaneous actions and cash-in-lieu outcomes require further modeling
and are rejected. Large distributions (at least 25% of the previous close) and
payable dates preceding ex-dates are rejected rather than applying ordinary rules
to due-bill events. See [SEC dividend-date guidance](https://www.investor.gov/introduction-investing/investing-basics/glossary/ex-dividend-dates-when-are-you-entitled-stock-and).

## Saved engineering samples

XLF, January 1 to March 1, 2025 (exclusive end), yields 39 actual sessions. It was
chosen to test calendar handling and affordable whole-share accounting, not for a
profitable signal. It is a sector ETF, not a proposed investment or a representative
universe. [Issuer instrument description](https://www.ssga.com/us/en/individual/etfs/state-street-financial-select-sector-spdr-etf-xlf)

The v0.3 sample extends through December 31, 2025: 250 sessions and four distributions.
Its split at July 1 is a fixed historical diagnostic, not a certified untouched
holdout. Parameters were not retuned after seeing its comparison. Neither sample
establishes an edge or supports walk-forward/multiple-testing conclusions.

The endpoint is unofficial and may change, throttle or stop responding. Public
availability does not establish redistribution rights. The downloaded copy is kept
locally for this user's research; do not publish it as a licensed dataset. There is
no paid feed or availability guarantee, and backtests never redownload mid-run.
