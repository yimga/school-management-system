# Studio OS — Structural Teardown Audit (v3.54.0)

**Generated:** 2026-05-21. Synthesizes the 6 per-section audits into one cross-section view.

## Classification axes

- **Architecture:** coherent / fragmented / template-only / missing-service / broken-wiring / stale-proof
- **UX:** premium / acceptable / dense / clipped / horizontally-broken / missing-primary-action / poor-mobile
- **Workflow:** clear-flow / partial / dead-end / missing-preview / missing-next-action
- **Engineering:** test-backed / untested / route-backed / template-only / hardcoded / unsafe-tenant-boundary
- **Action:** keep / minor-repair / aggressive-refactor / coordinator-task

## Section grades (post-v3.54.0)

| Section | Architecture | UX | Workflow | Engineering | Action taken |
|---|---|---|---|---|---|
| Overview | coherent | premium | clear-flow | test-backed | aggressive-refactor |
| Experience | coherent | premium | clear-flow | test-backed | aggressive-refactor + primary overflow owner |
| Automation | coherent | premium | partial (sim backend deferred) | test-backed | aggressive-refactor |
| Output | coherent | premium | partial → resolved (readiness wired in closeout) | test-backed | aggressive-refactor |
| Launch | coherent | premium | partial (timeline/approvals deferred) | test-backed | aggressive-refactor |
| Control | coherent | premium | clear-flow | test-backed | aggressive-refactor |

## Before / after per section

### Overview
- **Before:** fragmented — inline mode-cards + ops-hubs rows in shell.html; no next-best-action hero; no triptych; right-rail fell through to generic message
- **After:** command-cockpit composition; honest `data-state="unknown"` signal placeholders; PII-safe right-rail audit; new `{% elif not current_mode %}` Overview branch

### Experience
- **Before:** 10 overflow risks catalogued (file:line in audit JSON); workbench context column under-built; iframe lacked responsive shell
- **After:** 9 fixes in section files + 1 systemic at shared rail rule (`studio-mode-rail.css:5-20`); real workbench context column (state badges, tokens, preview-as-role, history, audit, related, Customizer CTA); clamp+aspect-ratio iframe

### Automation
- **Before:** missing simulation preview pane; rail less complete (8 sub-tools); dependency graph could overflow at narrow viewport
- **After:** honest "Simulation engine coming online" preview pane; 13-tool rail; `.rmc-automation-graph-scroll` wrapper (`overflow-x:auto; overflow-y:visible` — applies v3.27.1 sticky+clip lesson)

### Output
- **Before:** missing readiness summary service; pass-through inner partials (siteconfig/portal) could carry wide tables; iframe fallback risked fixed-width
- **After:** `.rmc-output-passthrough` wrapper (`min-width:0; overflow-x:auto`) around inner partials WITHOUT touching them; readiness summary service wired in v3.54.0 closeout (`get_output_readiness_summary`); aspect-ratio iframe fallback

### Launch
- **Before:** "Apply" surfaced as a fake path (apply_api returns 501); plan body lacked honest state; school infrastructure body had unresponsive diff table
- **After:** Apply explicitly operator-gated + `data-rmc-confirm`-gated as "Request platform apply"; plan body shows honest "Coming soon" card with tenant/operator split; `.rmc-launch-table-scroll` wraps infra diff table; readiness summary wired in closeout

### Control
- **Before:** rail had no-URL items; audit list rendered raw email (PII concern); no governance preview pane; permission-matrix could overflow
- **After:** rail items have real URLs (no-URL items dropped); external feature-control bridge link; PII-safe `actor_display` field; governance preview pane (proposed change + impact + dependency + audit-trail + rollback plan); perm-gated rollback CTA; `.rmc-control-permission-matrix-wrap` with `overflow-x:auto`

## Coordinator integrations (single-point or shell-level)

1. [`static/css/studio-mode-rail.css:5-20`](../../static/css/studio-mode-rail.css) — shared rail overflow safety (**systemic fix**)
2. [`templates/studio_os/shell.html`](../../templates/studio_os/shell.html) — Overview include + right-rail Overview branch + PII-safe actor + dead-elif removal + overview CSS link
3. [`apps/studio_os/views.py`](../../apps/studio_os/views.py) — `overview_signals` + launch mirror + `output_readiness_summary` + `launch_readiness_summary` wirings
4. [`apps/studio_os/services.py`](../../apps/studio_os/services.py) — `get_overview_signals` / `get_output_readiness_summary` / `get_launch_readiness_summary` + paused/failing extension to automation health
5. [`static/js/_pages/studio_os__shell.js`](../../static/js/_pages/studio_os__shell.js) — shared `data-rmc-confirm` capture-phase handler
6. [`static/js/service-worker.js`](../../static/js/service-worker.js) — `CACHE_VERSION` bump
7. [`docs/CSS_RETIREMENT_DOCKET.md`](../CSS_RETIREMENT_DOCKET.md) — § v3.54.0 entry
8. [`docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md`](../RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) — § batch 1373
9. [`docs/RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md`](../RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md) — § Slice batch 1373
10. [`memory/project_studio_os_next_realm_v3_54_2026_05_21.md`](../../../memory/project_studio_os_next_realm_v3_54_2026_05_21.md) + MEMORY.md index
11. [`templates/studio_os/partials/cockpit_copilot_rail.html`](../../templates/studio_os/partials/cockpit_copilot_rail.html) — pre-existing v3.53 `href="#"` anchor → `<button>` (closeout fix)
