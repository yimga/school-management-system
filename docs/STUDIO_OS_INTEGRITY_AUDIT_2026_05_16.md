# Studio OS integrity audit — 2026-05-16 (v2.73)

Static integrity pass on the Studio OS surface. Confirms every link,
form, and embedded subpage resolves; counts test coverage; calls out
what remains for live browser QA.

## Inventory

| Asset            | Count | Notes                                              |
|------------------|-------|----------------------------------------------------|
| URL routes       | 43    | All `name=` attributes present; no anonymous paths |
| Templates        | 58    | 4 mode templates + 1 shell + 21 subpage templates + 32 partials/components |
| Python modules   | 7     | `urls.py`, `views.py`, `services.py`, `school_infrastructure.py`, `deep_links.py`, `apps.py`, `__init__.py` |
| Test modules     | 13    | `tests/test_*.py`                                  |
| Test functions   | 51    | One test file per major surface area               |

### Mode taxonomy

Studio OS exposes 5 modes, each routed through the same `studio_shell`
view with a kwarg:

| Mode       | Path           | Canvas template                                   |
|------------|----------------|---------------------------------------------------|
| Launch     | `/studio/launch/`     | `partials/launch_mode_canvas.html`         |
| Experience | `/studio/experience/` | `modes/experience.html`                    |
| Automation | `/studio/automation/` | `partials/automation_mode_canvas.html`     |
| Output     | `/studio/output/`     | `partials/output_mode_canvas.html` (dedupe'd in v2.70) |
| Control    | `/studio/control/`    | `partials/control_mode_canvas.html` (Wave A treated in v2.64.1) |

Each mode has sub-routes (`/experience/recommendations/`,
`/automation/conflict-detection/`, `/output/branding-inheritance/`,
etc.) and corresponding subpage partials under
`templates/studio_os/partials/subpages/`.

### Hub routes

Three workflow hubs are mounted under `/studio/hubs/`:

- `/studio/hubs/approvals/` → `approval_workflow_hub`
- `/studio/hubs/workflow/`  → `workflow_center`
- `/studio/hubs/import/`    → `import_hub`

These import from `apps.accounts.views_workflow` — shared with the
control plane, not Studio-specific.

### API endpoints

- `POST /studio/save-draft/`
- `POST /studio/publish/`
- `POST /studio/rollback/`
- `GET  /studio/version-history/`
- `GET  /studio/search/`
- `GET  /studio/recommendations/`
- `GET  /studio/preview/`
- `GET  /studio/audit/`
- `POST /studio/api/school-infrastructure/preview/`
- `POST /studio/api/school-infrastructure/validate/`
- `POST /studio/api/school-infrastructure/apply/`

## Link / form integrity

`scripts/audit_route_surface.py` (run in v2.71) confirmed:

- **0 broken `{% url %}` refs** anywhere in the 58 templates.
- **0 broken Python `reverse()`** in `apps/studio_os/views.py` /
  `deep_links.py` / `services.py`.

Studio OS templates participated in the platform-wide 6,081-route
audit — the surface is link-integrity clean.

## Test coverage

13 test modules, 51 test functions:

| Test module                                       | Surface covered                         |
|---------------------------------------------------|-----------------------------------------|
| `test_launch_and_automation_rails.py`             | Left-rail resolution for launch + automation modes |
| `test_studio_rail_resolution.py`                  | General rail resolution + active-pane highlighting |
| `test_output_native_builder.py`                   | Native body builders for output panes   |
| `test_experience_workbench.py`                    | Experience workbench context shaping    |
| `test_experience_rollback.py`                     | Experience pack rollback flow           |
| `test_batch949_experience_compare_view.py`        | Experience compare view (regression)    |
| `test_batch963_command_palette_launch_panes.py`   | Cmdk → launch pane wiring (regression)  |
| `test_phase_05_granular_taskers.py`               | Phase 5 taskers                         |
| `test_phase5_mechanical_gate.py`                  | Phase 5 mechanical gate                 |
| `test_cp_bridge_policy_1100.py`                   | Control plane bridge policy             |
| `test_school_infrastructure.py`                   | School infrastructure preview/apply/validate APIs |
| `test_deep_links.py`                              | Deep-link routing                       |
| `test_preview_context.py`                         | Preview rendering context               |

Coverage gaps (no dedicated test module):

- `studio_publish_api` / `studio_save_draft_api` / `studio_rollback`
  (publish/draft/rollback) — likely exercised inside the workbench
  tests but no isolation-level test exists.
- `studio_global_search` / `studio_recommendations_api` — same.
- `studio_audit_api` — same.

These are reasonable follow-ups for a dedicated test wave, not
blockers for this audit.

## v2.73 fixes shipped alongside the audit

Three real findings from `audit_page_standards` (v2.71 baseline)
plus the one real `audit_no_placeholder` finding were closed:

1. **`templates/portal/seating_chart.html`** — replaced the "Coming
   soon" alert with a clear paragraph + CTA to `take_student_attendance`
   with the classroom pre-filtered. No more apology copy.
2. **`templates/migration_cloud/console.html`** — outer `<section>`
   promoted to `<main id="main">` for landmark accessibility.
3. **`templates/migration_cloud/bundle_detail.html`** — same.
4. **`templates/migration_cloud/anomaly_nudge.html`** — same.

Re-run results:

- `audit_page_standards`: 9 findings → **6 findings** (all 3 missing
  main landmarks closed; remaining 6 are `inline_script_count`
  legitimate small inline scripts — drift-only, not regressions).
- `audit_no_placeholder`: 3 findings → **2 findings** (the seating
  chart "Coming soon" is gone; remaining 2 are false positives in
  templates that legitimately describe "sample data" affordances).
- `audit_template_render_safety`: 0 findings (no syntax broken by the
  edits).

## What this audit does NOT prove

- **Live link clicking.** Static URL resolution ≠ user-visible
  behavior. A view can resolve but return 500. Need authenticated
  browser harness to confirm.
- **Premium feel.** The user explicitly asked Studio OS to "feel
  premium and creative." That's a design review, not a static
  audit. v2.64.1 polished the Control canvas; the other 4 modes
  have the same grammar but a polish pass per mode is a separate
  wave (each mode is ~1-2h of UX work).
- **Mobile QA.** Responsive behavior on small screens needs a real
  browser. The dedupe in v2.70 (output canvas rail vs tabs) is the
  one mobile-specific fix this session shipped.

## Recommendations

1. **Add a dedicated test module for publish/save-draft/rollback
   APIs** (3 endpoints, ~10 tests). These are the state-changing
   APIs Studio OS gates on — worth isolated coverage.
2. **Add `studio_audit_api`, `studio_global_search`, and
   `studio_recommendations_api` tests** — currently no isolation
   coverage.
3. **Polish wave per non-Control mode** — Apply v2.64.1's
   disclosure/bento patterns to Launch, Experience, Automation, and
   Output canvases. The Output canvas already got rail/tabs dedupe
   in v2.70. Each remaining mode is its own ~1-2h wave.
4. **Browser axe + auth integration test harness** — biggest gap
   in this audit's coverage. Without it, "every link works" claims
   only mean "every link resolves at the URLconf layer."
