# Studio OS Control — Next-Realm Audit v3.54

Date: 2026-05-21
Agent: Agent 6 — CONTROL section
Mission: rebuild Studio OS Control into a governance cockpit.

## 1. Owned files

- `templates/studio_os/modes/control.html`
- `templates/studio_os/partials/control_mode_canvas.html`
- `templates/studio_os/partials/workspace/control_canvas.html`
- `templates/studio_os/partials/workspace/control_rail.html`
- `static/css/studio-control-cockpit.css` (NEW)
- `templates/studio_os/partials/control_governance_preview_pane.html` (NEW)
- `apps/studio_os/tests/test_studio_control_inline.py` (extend)
- `apps/studio_os/tests/test_control_governance_cockpit.py` (NEW)

## 2. Control surface inventory

The `studio_shell` view (`apps/studio_os/views.py:1296`) builds the control-mode context block at lines 1907-1980. Context vars surfaced for `mode='control'`:

| Var | Source | Notes |
|---|---|---|
| `control_audit_entries` | `get_feature_control_audit_entries(request, limit=15)` (siteconfig.views_feature_control:1580) | Returns `id, action, created_at, user_id` only. NO email/slug leakage by construction. Empty list on import/attribute failure. |
| `control_left_rail` | `build_control_governance_rail(request)` (studio_os.navigation:34) | 11 entries: Config center, Feature control, Audit log, Runtime inspector, Metadata governance, Lineage, Integrations, Blueprints, Policy diff, Plans, Impact, AI cleanup. |
| `control_outcome_sections` | `build_control_studio_rail_sections(request)` (siteconfig.control_outcome_center:507) | 9 outcome groups w/ links per group. |
| `why_enabled_summary` | `WHY_ENABLED_SUMMARY` constant (siteconfig.control_outcome_center:384) | Translatable rationale string. |
| `operator_control_model` | `build_operator_control_model_for_request(request)` | 6-paragraph educational copy. |
| `control_outcome_hub` | Always `[]` v3.53 | Placeholder. |
| `control_panel_html` | Rendered `feature_control_panel_partial.html` ONLY when `request.user.has_perm("settings.feature_control")` | Already gated. |
| `embed_url` | `None` when `control_panel_html` is populated | Avoids double-render. |

Subviews:

- `studio_system_config_console` — read-only link list (manager-host fallback).
- `studio_control_impact` — preview-pane data (`impact_summary`, `dependency_warnings`).
- `studio_ai_cleanup` — read-only suggestions.
- `studio_audit_api` — JSON list; returns `[]` for unauthenticated (graceful).
- `studio_rollback` — control mode redirects to siteconfig:feature_control_panel (no direct write).

External hubs (link OUT, never duplicate):

- `legacy_urls.feature_control` — feature toggle SOT.
- `siteconfig:feature_control_audit` — paginated full log.

## 3. Horizontal overflow risks

| Site | Risk | Owner | Fix |
|---|---|---|---|
| Audit list rows in `studio-os__right` sidebar (shell.html:255-260) | Action text + timestamp wrap at <360px | Agent 1/2 (coordinator) | Document only — we add safe rendering in our preview pane and canvas. |
| Bento chiplet rows in outcome bento | Wide chiplet rows wrap inside auto-fit cells | None | Existing CSS accommodates. |
| Permission matrix (proposed) | N x M table 12+ columns | Agent 6 | Wrap in `.table-responsive`/`.rmc-control-permission-matrix-wrap { overflow-x:auto }`. |
| Dependency graph teaser | Long node labels overflow | Agent 6 | `min-width:0; overflow-wrap:anywhere` on `.rmc-control-dep-node`. |

## 4. Governance model

Audit data exists (`FeatureControlAudit`). The accessor returns only `(id, action, created_at, user_id)` — safe from PII leakage by design. Rollback is **not** wired directly inside Studio for control mode; the redirect pattern routes operators to `siteconfig:feature_control_panel` where the Revert button enforces `settings.feature_control` permission. Feature flag SOT is **outside** Studio. We bridge to it; we never duplicate the toggle UI here.

## 5. Permissions visibility

Today's Studio Control has zero permission visibility. Operators must context-switch to RBAC. The CI scanner `audit_role_permission_matrix.py` already writes `docs/generated/role_permission_matrix.{json,csv}` but Studio Control does not link to it. **Action**: add a Permission overview tile that links to `legacy_urls.rbac` and, when present, to the generated matrix file path (download). Always under permission gate.

## 6. Risk state

No risk-state engine exists today. `why_enabled_summary` is rationale copy. `control_audit_entries` is recent activity, not risk. **Honest deferral**: render "Risk monitor coming online" empty state in the risk tile, with a placeholder for: pending rollbacks count, active critical flags, recent destructive actions, audit-chain integrity. Future v3.55+ work to wire a real aggregator.

## 7. Destructive actions

| Action | Today | v3.54 enhancement |
|---|---|---|
| Rollback | GET-redirect to feature control panel | Add explicit confirm CTA in preview pane + permission gate `{% if perms.settings.feature_control %}` before showing the button. |
| AI cleanup | Read-only suggestions | None — already safe. |
| System config console | Link list | None — each link enforces own perm. |

## 8. Required actions

A. Promote control canvas to a governance cockpit grid (audit + risk + permission + dep-graph + feature-flag bridge tiles).
B. New `control_governance_preview_pane.html` — proposed-change + impact + affected + audit-trail preview + rollback plan + confirm CTA.
C. Render `control_audit_entries` safely — no raw email/slug.
D. Control rail keeps its 11 entries; add "Manage in Feature Control" link (already present via `siteconfig:feature_control_panel`) external; remove any dummy hrefs.
E. New `static/css/studio-control-cockpit.css`; link from `modes/control.html`.
F. New test file `test_control_governance_cockpit.py`.
G. Coordinator-task: a tiny CSS cleanup nudge for `studio-control-mode-canvas.css` is NOT required this wave; we just link a parallel file.

## 9. Scanner risk posture

All 32 zero-tolerance gates remain at 0. Our new code:

- Uses `{% trans %}` + `var(--*)` only (no inline literals, no role-string literals).
- Defines every `.rmc-control-*` class in our new CSS file.
- Renders audit rows from already-PII-clean data (`get_feature_control_audit_entries` returns no email/slug).
- Adds no `<style>` blocks, no `defer/async` on shell scripts.
- Adds no logger calls.

## 10. What I did NOT do

- Did not edit shell.html / shell_control_plane.html / cockpit_*.html (other-agent ownership).
- Did not edit existing studio-control-inline.css or studio-control-mode-canvas.css (read-only per ownership).
- Did not bump service worker.
- Did not touch CLAUDE.md / MEMORY.md / CSS_RETIREMENT_DOCKET.md.
- Did not duplicate the feature-control toggle UI.
- Did not invent risk-state data — used honest empty state.
- Did not execute Django tests.
