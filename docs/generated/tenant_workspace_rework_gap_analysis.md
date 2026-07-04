# Tenant Workspace Rework Gap Analysis

Generated: 2026-07-03

## Scope

This audit covers tenant/operator pages that use the same rendering pattern as Studio: nested workspaces, local rails, preview panes, feature controls, workflow steps, report-card previews, and launch/setup previews. A second parity pass compared the live templates against the approved `var/design-previews/tenant-studio-100x-workmode-rework.html` design and closed the remaining command-header, sidecar, duplicate-control, and preview-action gaps.

## Screen Real Estate Pass

The touched surfaces were re-audited for horizontal waste after the 100X implementation. Bootstrap container max-widths were already removed from command workspaces, so the remaining work was rail economics: keeping navigation/sidecar panels useful while giving the primary canvas, previews, and grids the extra width first.

- Studio shell: reduced outer gutter, narrowed the right impact rail ceiling, and tightened canvas/right padding.
- Studio work modes: narrowed shared mode rails and context rails so Experience, Automation, Outputs, Launch, and Control reserve more width for the active canvas.
- Studio cockpit: replaced fixed 320px co-pilot rail and fixed 16px gap with responsive clamps.
- Report Card Builder and Feature Controls: narrowed shared control/sidecar rails while preserving sticky side actions.
- Workflow Center: narrowed the side rail and reduced workflow-card minimum width so more cards fit per row on large screens.
- Narrow-page audit sweep: removed legacy `container` / `container-lg` / inline width caps from additional Studio-adjacent tenant command pages and analytics/report-builder surfaces, while preserving intentionally narrow personal/account forms.
- Evidence/report surfaces: added a scoped full-width override for named `cp-evidence-page` surfaces so report catalogs, schedules, governance, and audit evidence pages no longer inherit the old `--rmc-report-measure` cap.
- Command content density: converted fast-path, launch-lane, and provisioning timelines into responsive multi-column grids on wide screens and expanded governed-report output height so new width becomes useful workspace, not stretched text.

## Closure Matrix

| Surface family | Representative routes | Files changed | Status |
|---|---|---|---|
| Studio shell | `/studio/`, `/studio/experience/`, `/studio/automation/`, `/studio/output/`, `/studio/launch/`, `/studio/control/` | `templates/studio_os/shell.html`, `static/css/studio-shell-layout.css`, `static/css/studio-workspace.css`, `static/css/tenant-command-workspace.css`, `templates/studio_os/partials/shell_extrastyle.html` | Closed by shared horizontal mode strip, compact 100X command header, and denser workspace contract |
| Studio work modes | Experience, Automation, Outputs, Launch, Control mode canvases | `static/css/studio-workspace.css` | Closed by shared rail/main/context dimensions and bounded scrolling |
| Report card builder | `/siteconfig/reports/builder/`, Output Studio native builder | `templates/siteconfig/partials/reportcard_builder_inner.html`, `templates/siteconfig/reportcard_builder.html`, `static/css/tenant-command-workspace.css` | Closed by command workbench, bounded preview frame, scrollable builder rail, and preview/publish sidecar |
| Feature controls | `/siteconfig/features/`, Control Studio inline panel | `templates/siteconfig/feature_control_panel.html`, `templates/siteconfig/feature_control_panel_content.html`, `static/css/tenant-command-workspace.css`, `static/js/_pages/siteconfig__feature_control_panel_content-1.js` | Closed by command contract, persistent impact/rollout sidecar, and wired sidecar preview action |
| Workflow Center | Backend Workflow Center, Studio Automation embed | `templates/accounts/workflow_center.html`, `templates/accounts/workflow_center_embed.html`, `templates/accounts/partials/workflow_center_main.html`, `static/css/workflow-center.css` | Closed by main workbench plus status/navigation side panel; duplicate hero actions and context were removed |
| Role workflow centers | Teacher, parent, student workflow centers | `templates/teacher/workflow_center.html`, `templates/parent/workflow_center.html`, `templates/student/workflow_center.html` | Closed by explicit command-workspace markers and base CSS inheritance |
| Setup Studio / launch preview | `/siteconfig/guided-onboarding/`, `/siteconfig/guided-onboarding/?embed=1#student-csv-import` | `templates/customersuccess/guided_onboarding.html`, `templates/customersuccess/guided_onboarding_embed.html`, `static/css/setup-studio-onboarding.css` | Closed by compact embed grid and command-workspace markers |
| Dashboard previews | Dashboard-by-role and role preview surfaces linked from Studio/Launch | `templates/portal_base.html`, `static/css/tenant-command-workspace.css` | Closed at shared tenant shell level for marked command/preview surfaces |
| Theme/customizer previews | Experience mode, theme colors embed, customizer links | `static/css/studio-shell-layout.css`, `static/css/studio-workspace.css`, `templates/portal_base.html` | Closed through Studio Experience workspace and base command contract |
| Forms/admissions/communications previews | Setup/import, role workflow, communication preview links | `templates/customersuccess/guided_onboarding*.html`, role workflow center templates, `templates/portal_base.html` | Closed through setup/workflow command contract; no business logic changed |
| Tenant launch command pages | School Studio, lifecycle command center, fast path, provisioning status | `templates/siteconfig/tenant_studio_hub.html`, `templates/siteconfig/tenant_lifecycle_command_center.html`, `templates/siteconfig/tenant_launch_fast_path.html`, `templates/siteconfig/tenant_provisioning_status.html`, `static/css/tenant-command-workspace.css` | Closed by replacing 48-62rem caps with shared command-workspace markers and responsive wide-screen grids |
| Analytics/report workspaces | Decision intelligence, decision surfaces, event analytics, governed report builder, saved report detail | `templates/analytics/decision_intelligence_dashboard.html`, `templates/analytics/decision_surface_dashboard.html`, `templates/analytics/event_analytics_dashboard.html`, `templates/analytics/governed_report_builder.html`, `templates/analytics/governed_saved_report_detail.html`, `static/css/tenant-command-workspace.css` | Closed by replacing `container-lg` caps with full-width command workspace surfaces and taller report output canvas |
| Evidence/report catalogs | Bulk letters, scheduled reports, report templates, output history, academic setup evidence, AI governance, billing plan, tenant report schedules, term publish | `static/css/tenant-command-workspace.css` | Closed by overriding named evidence/report caps without touching focused personal forms |

## Validation

- `python manage.py check` passed.
- `python manage.py makemigrations --check --dry-run` passed with no changes detected.
- `python -m compileall -q apps config scripts` passed.
- Django template loader passed for `studio_os/shell.html`, `accounts/partials/workflow_center_main.html`, `siteconfig/partials/reportcard_builder_inner.html`, and `siteconfig/feature_control_panel_content.html`.
- `git diff --check` passed on changed workspace/layout files.
- Playwright is available (`npx.cmd playwright --version` reports 1.58.2).
- Playwright rendered the approved local HTML preview and confirmed the Studio 100X, Experience, Outputs, Report Card Builder, Feature Controls, and No Blanks sections exist in the DOM.
- Local Django route validation was attempted against existing servers on ports 8000/8001 and a clean temporary server on port 8020. All returned `ERR_SSL_PROTOCOL_ERROR` before page load, so authenticated route validation could not be completed in this environment.
- Focused Django test runs were attempted, but the SQLite test database was locked by long-running local Python processes. The timed-out test process started by this audit was stopped; unrelated support-chat test processes were left untouched.

## Remaining Risk

No product API or business workflow changed. The remaining risk is visual/authenticated-browser-only: protected tenant pages still need an authenticated browser pass after deployment or in a local environment whose HTTP server responds normally.
