# Dashboard verification — 2026-09-11

The implementation uses the generated dashboard concept as its visual direction,
with deliberate changes for real state and the research-only execution model.
Generated images and browser captures stay local and are excluded from Git.

Local evidence in this directory:
- `dashboard-concept.png`: generated 1505 × 1045 concept, inspected with `view_image`.
- `dashboard-desktop.png`: full-page Browser/IAB screenshot at a 1505 × 1045 viewport.
- `dashboard-preview.png`: desktop viewport capture.
- `dashboard-mobile.png`: full-page capture at a 390 × 844 phone viewport.

Browser/IAB was used directly, with its Playwright locator API for repeatable tests.
Both the concept and implementation captures were inspected with `view_image` in the
same QA pass. No external Playwright/browser automation fallback was needed. Temporary
viewport overrides were reset after verification.

## Fidelity ledger

| Comparison | Concept evidence | Implementation evidence | Resolution |
|---|---|---|---|
| Navigation | Overview, Portfolios, Jobs, Research, Experiments | Same five tabs with a teal selected state | Preserved; each tab changes real local content |
| Structure | Header, heading, notice, metric strip, portfolio/health columns, experiments, jobs | Same order and two-column desktop layout | Preserved; full page is taller because it includes actual rows and explanatory text |
| Typography | Dark sans-serif heading and readable table labels | Segoe UI/system font; restrained heading hierarchy, 13px tables and explicit form fonts | Intentional smaller type and horizontal desktop brand subtitle; phone subtitle stacks |
| Palette | White/slate surfaces, navy text, teal action and amber notice | Same palette roles, thin gray borders and small corner radii | Preserved; no decorative background imagery or animation |
| Copy | Historical demo notice, Positions, dummy XLF research row | Explicit historical/paper notice, Units held, actual account IDs and saved balances | Intentional correctness change: do not confuse units with number of positions or pool separate capital |
| Data density | One portfolio, one experiment, no jobs | Two independent historical accounts, latest three reports and one recurring audit | Real state replaces concept placeholders; all reports remain accessible on Experiments |
| Source label | Saved snapshot | Checked vendor snapshot | Replaced an internal underscored classification with readable text; exact metadata remains in account details |
| Controls | Refresh, filters, View all, report link | Refresh, functional name/strategy/status filters, tabs, account/job/research detail dialogs and report links | Tabs replace redundant View all controls; no inert action buttons |
| Assets | Diagram-like UI, warning/search icons | Native HTML/CSS, no raster UI; text notice and labeled search | Intentional icon omission; accessible labels carry meaning |
| Mobile | No separate phone concept | Single-column panels, two-column metrics, horizontally scrollable tables and navigation | Tested at 390px; no document-level horizontal overflow |

Above-the-fold copy diff: tab order, product name, overview heading and Refresh remain.
The notice now spells out paper simulation and lack of profitability evidence. A subtitle,
update timestamp and explicit selected-account label were added. Units held replaces
Positions. Values come from SQLite. These are intentional functional deviations, not
unreviewed marketing copy. The layout is faithfully verified against the concept's
structure and palette, with the typography, copy, icon and data-density differences
listed above; it is not claimed as a pixel-identical reproduction.

## Functional paths verified

- Search with no matches displays an empty state; restoring XLF restores the rows.
- Strategy filtering removes the cash row and retains the trend row.
- The trend account opens revision 2 with its twelve fills, equity curve, rules and
  pending/rejected orders. Cash opens an empty fill ledger without inventing trades.
- Jobs opens the stored lease/retry state and completed audit result.
- Research opens the critique imported from the current Codex session, including its
  untrusted-text label and frozen evidence.
- Mobile navigation reaches Experiments; the latest report opens and exposes its
  walk-forward ledger and uncertainty links.
- Browser console contained no warnings or errors in the verified dashboard session.
- Windows hidden-process start, stop and restart were exercised; no power settings
  or repository permissions were changed.

Numerical and HTTP security behavior is covered separately by the automated suite.
Visual checks do not establish financial correctness or profitability.
