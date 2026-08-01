# Tenant layout balance — audit before approval

Status: prototype only. No production template or stylesheet has been changed by this approval slice.

## What the screenshots expose

1. Setup cards occupy roughly the left two-thirds of the available tenant canvas while their parent surfaces span almost the full width. The unused right area is accidental, not useful negative space.
2. Fixed-count grids and narrow card sizing are the dominant structural cause. Centering rules in `rmc-tenant-dashboard-balance.css` center content inside components but do not make the overall composition balanced.
3. Admin deep links are rendered as a detached button row in `templates/accounts/backend_dashboard.html`. They are global/contextual commands and should live in the masthead command area or a compact overflow group.
4. The page stacks many full-width bordered bands. Journey, readiness, setup, stage navigation, and stage cards have comparable visual weight even though their operational priority differs.
5. Several actions are repeated as card CTAs, standalone links, tabs, sidebar links, and edge tools. The result is more chrome than decision support.
6. The shell has multiple edge/floating affordances. Page-level controls should not compete with shell utilities.

## Repository evidence

- `templates/accounts/backend_dashboard.html` contains a standalone four-button “Admin deep links” row.
- `templates/partials/tenant/setup_command_surface.html` renders setup choices and every wizard stage with the same card-list primitive.
- `static/css/rmc-tenant-dashboard-v2.css` uses fixed four- and six-column desktop grids.
- `static/css/rmc-tenant-dashboard-balance.css` applies broad centering to multiple unrelated card types.
- `static/css/dashboard-auto-grid.css` has a better `auto-fit/minmax()` foundation but it is not the universal archetype contract.
- `docs/UX_PAGE_AUDIT_CHECKLIST.md` already forbids button gardens, but it does not measure occupied width, imbalance, orphan actions, incomplete rows, or floating-control duplication.

## Proposed design law demonstrated by the prototype

- A wide tenant canvas uses a deliberate bento composition rather than a stack of equally weighted full-width bands.
- The next task owns the largest region; KPIs and passive status use smaller supporting regions.
- Cards use adaptive `auto-fit/minmax()` behavior and the final item fills or balances its row.
- Related actions live where their context lives. One primary command is visible; secondary commands are grouped.
- One shell utility dock is allowed. Page-specific floating button clusters are removed.
- On small screens the visual hierarchy becomes a single semantic sequence with no overlap or horizontal scroll.

## Approval choices

Open `tenant-layout-balance-preview.html` and review both tabs:

- **Setup Studio:** replaces the sparse four-card band and detached activation link with an asymmetric “recommended path + supporting methods” workspace.
- **Admin Home:** replaces detached deep-link buttons and uniform bands with one command header, an action queue, a balanced KPI strip, and a contextual activity/finance split.

Approval of this artifact authorizes cleanup of sizing, alignment, spacing, wrapping, spanning, and visual finish only. It does not authorize rebuilding pages, changing information architecture, removing controls, hiding buttons, or altering workflows. The full rollout must use the aggressive audit prompt and preserve every existing function unless a separate change is explicitly approved.
