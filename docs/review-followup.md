# Review follow-up

The review identified three reproducible defects. Each now has a regression test.

| Defect | Correction | Evidence |
|---|---|---|
| Input could change between computation and saving | Frozen Dataset derives bars and hash from one byte payload; result carries the parsed-bar fingerprint | Replacing the original file cannot change saved input; results from different bars are refused |
| Baseline changes reused stale cached reports | Every result's implementation, parameters and execution config enter identity; all new artifact bytes are compared with saved bytes | Changed baseline produces a different ID; changed output under an identical specification raises an error |
| Installed demo couldn't find its fixture | CSV and calendar are packaged resources | A real wheel is built offline and its declared entry point runs from an isolated installed layout |

Additional issues found and fixed during implementation:
- End-of-day volume was used to decide an opening fill. Zero-volume datasets now
  fail admission instead of changing an individual opening execution decision.
- Caller Decimal rounding and exception traps leaked into calculations. Engine,
  metrics and standalone indicators now use an explicit fixed context.
- Checksums alone accepted an altered checksum inventory. Expected artifact names
  and this computation's bytes are now compared exactly on result reuse.
- Mid-write failures could leave half-published reports. Artifacts now publish via
  a same-filesystem rename; a failed staging write leaves no final bundle.
- Private Windows temporary-directory permissions survived publication and blocked
  the sandbox worker from reading a network-created snapshot. Staging now inherits
  workspace permissions through a normal directory; the existing snapshot was repaired.
- Source edits in an active process could mislabel evidence. Loaded source identity
  is checked before computation and saving; changed code requires a restart.

The tests include accounting examples, future-data mutation, retest expiry and
invalidation, gap losses, cash constraints, holiday/early-close/DST behavior, missing
sessions, reported corporate actions, malformed provider data, snapshot tampering,
cache mismatches, interrupted publication and installed-package execution.

Remaining scope limits are explicit: one instrument per simulation, close-based
exits, no partial fills/impact, cash interest or live orders, no corporate-action
ledger, a bounded 2025–2026 calendar, and no statistical strategy validation. The
20% entry allocation does not cap subsequent appreciation. Results are engineering-only.

The earlier `demo-results/` bundle is retained as historical evidence from version
0.1, not overwritten. Use new reports under `demo-results-v2/` and `market-results/`.
