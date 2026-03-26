# Premium UX manual pass (BR-13)

## Repo program checklist — machine-verified (closure)

These items are **closed for the repository program** when the commands below pass on a migrated gate database. Evidence is recorded in [RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md](RUNMYCAMPUS_AUTONOMOUS_EXECUTION_LOG.md) (wave B2 / final sweep).

- [x] **`data-page-archetype` / shell contract on audited surfaces** — `python scripts/verify_ux_completion.py` (with `DJANGO_UX_AUDIT_USE_GATE_DB=1` and `DJANGO_TEST_DB_FILE` set after `migrate_gate_test_db.py`), bundled inside `python scripts/verify_operator_phase10_11_e2e.py`; plus `python scripts/audit_phase3_phase4_surfaces.py` for template inventory.
- [x] **Studio OS / dashboard / setup product markers** — same `verify_ux_completion.py` checks (`dashboard.*`, `setup.*`, required private templates).
- [x] **No broken placeholder copy on proof / marketing / marketplace surfaces** — static template reads + route marker checks in `verify_ux_completion.py` and Phase 10/11 pytest bundle.
- [x] **Focus-visible / keyboard / a11y baseline** — Phase 2 design-system gate `python scripts/verify_design_system_phase2.py`; Phase H static slice inside `python scripts/verify_phases_3_11_gates.py`; north-star a11y lint where wired in that bundle.
- [x] **Responsive / layout contracts (automated surrogate)** — `platform-fluid-everywhere` and related checks in `verify_phases_3_11_gates.py` where present; dashboard density `python scripts/verify_phase8_dashboard_density.py`.
- [x] **Low-click / role-home spine** — `apps/dashboard/tests/test_role_home_engine.py`; `apps/schools/tests/test_primary_control_plane_nav.py`; `apps/schools/tests/test_control_plane_nav_roles.py`; `verify_ux_completion.py` role-home contract.

**Last full chain PASS:** 2026-03-25 — `verify_operator_phase10_11_e2e.py --ux-db-file .django_test_dbs/rerun_closure_20260325.sqlite3` (51 tests + UX audit **OK**).

## Touring (product surfaces)

- **Super (control plane):** **Page tour** on `/super/trust/`, `/super/migration/csv-diff/`, `/super/tools/governed-query/` → `siteconfig:tour_steps_api?context=super_trust|super_migration|super_governed` + `static/js/control-plane-tour.js`.
- **Tenant backend:** `tour_steps_api?context=backend_dashboard` + first-login tour (unchanged).
- **Setup Studio** linked from Configuration Control Center outcome banner (`console_domains_hub`).

## Production release sign-off (organizational — not a repo checkbox)

Before tagging a **production** release, product and design record **date + initials** here (or in your release ticket). This is **outside** the autonomous repo gate program and does not block merge when the checklist above is green.

```
Release tag: _______________
Product initials: _______________
Design initials: _______________
```

**Note:** CI and the scripts above do not replace a human walkthrough of live styling and copy on a staging host; they **do** close the **in-repo** BR-13 bar for merge and autonomous execution prompts.
