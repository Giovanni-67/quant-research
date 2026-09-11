# Make this a project you can explain and own

Using AI does not make the project worthless. Your credibility comes from accurately
describing your contribution and being able to explain, test, change and debug the
system. Running generated code alone does not demonstrate those abilities. There
is no need to pretend you wrote every line, and no need to discard useful work.

## Your first contribution: independently investigate ATR

The subsequent request to complete the platform means Codex has now implemented ATR
and its sizing integration in `risk.py`. Do not claim that implementation as your own.
Use this exercise to independently derive expected values and compare an independently
written version with the existing one. Keep your work separate from trading rules so
correctness can be assessed without looking at profitability.

1. Read `models.py`, the `sma`/`bollinger` functions, and `test_core.py`. Trace one
   close decision through next-open execution. Explain why a same-close fill would
   be a different execution assumption.
2. In an exercise branch, create your own volatility module and independent tests. Write a
   `wilder_atr(bars, window)` function. Return `None` until there are `window` true
   ranges. Use Decimal and the package's explicit numerical context.
3. Define the convention in your own words before coding: first true range is
   high minus low. Later true range is the maximum of high minus low, absolute
   high minus previous close, and absolute low minus previous close. Seed ATR with
   the arithmetic mean of the first `window` true ranges; later ATR is
   `(previous_ATR * (window - 1) + current_TR) / window`.
4. Calculate this fixture on paper before running code. Bar 1: O100 H105 L95 C100.
   Bar 2: O110 H112 L109 C111. Bar 3: O110 H113 L108 C109. Bar 4: O101 H103 L99 C102.
   All have positive volume and increasing dates. Use a window of 3. Explain why
   the overnight gap matters even when the second candle has a small range.
5. Write independent assertions for the hand-calculated output, insufficient
   history, invalid windows, constant prices and a changed future suffix. Changing
   future bars must not change any earlier ATR. State how split-adjusted history
   reaches the indicator so a share split does not look like volatility.
6. Write a short design note comparing Wilder smoothing with a rolling arithmetic
   mean. Explain that ATR describes historical price movement, not a guaranteed
   future loss bound. Show where it could later feed position sizing without
   allowing an LLM to calculate quantities.
7. Ask Codex to review your implementation, then explain and fix any findings.
   Keep the initial diff and your corrections in version control. Record the actual
   work and assistance in `CONTRIBUTIONS.md`.

Use AI for questions, feedback and counterexamples during this exercise. Try the
first implementation and expected-value calculations yourself. Passing assertions
copied from the same implementation is weak evidence; independent examples matter.

## A second contribution with more system ownership

Choose a reported limitation, reproduce it with a minimal case, write the intended
behavior, implement the change, and explain the tradeoff. Good candidates after ATR
are indicator warm-up contracts, a cost sensitivity experiment with all trials
reported, or a read-only comparison table for every strategy's ledger. Start small;
do not begin with real-money execution or an entire statistical validation framework.

You should eventually be able to demonstrate a failed data admission, explain why
it failed, trace a dividend from entitlement to cash, modify a strategy parameter,
and show how that modification changes the recorded experiment identity.

## Résumé and LinkedIn wording

Accurate now, if you want to list it while learning:

> Developing an AI-assisted Python quantitative research platform; defined scope,
> execution requirements and a separation between deterministic backtesting and
> AI-supported research.

After you complete the lab, replace generic ownership claims with your actual work:

> Implemented and independently tested a gap-aware volatility indicator in a Python
> research engine, including hand-calculated cases and checks against future-data leakage.

That second statement is a template, not a completed achievement. Other project
features may be described as system capabilities, but distinguish them from modules
you personally designed or implemented when asked. A short LinkedIn development
post can discuss what you learned, one bug, one test and how you used Codex.

Do not claim a profitable trading system, institutional production readiness or
independent authorship. Actual financial losses/profits are not required for this
to be a strong software-engineering project. Reproducibility, correctness and clear
technical reasoning are better current evidence.

Before publishing, use synthetic fixtures and code. Keep local vendor snapshots,
issuer workbooks, account information and secrets out of the public repository.
The project `.gitignore` excludes current market input/result directories.
