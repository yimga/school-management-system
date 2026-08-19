# Phase 10 — Marketplace / packs / migration / interop — checklist

**Status:** **DONE** (2026-03) — evidence in SOT **§3.2.3**, static gates, repo-wide audit, pytest slice via `scripts/verify_operator_phase10_11_e2e.py`.

## Python

- [x] `apps/marketplace/` — views, `listing_display.py`, `ecosystem_links.py`
- [x] `apps/packages/engine.py` — pack lifecycle
- [x] `apps/accounts/views_migration.py` / workflow views — migration UX

## Templates

- [x] Marketplace catalog / incident / dashboard templates
- [x] Package rollback UI: `templates/siteconfig/installed_packages_rollback.html`

## Tests

- [x] `apps/packages/tests/test_engine.py`
- [x] `apps/accounts/tests/test_migration_phase9_detection.py`

## Validation

- [x] `python scripts/verify_program_phase10_phase11_gates.py` + `python scripts/verify_repo_wide_ecosystem_marketing_audit.py` (in `verify_phases_3_11_gates.py`)
- [x] `python scripts/verify_operator_phase10_11_e2e.py` — **`migrate_gate_test_db` first** (dedicated `.django_test_dbs/operator_phase1011_e2e.sqlite3`), then pytest + **`verify_ux_completion`** (or `--skip-ux-completion` / `--ux-db-file`)
- [x] `python scripts/verify_ux_completion.py` with **`DJANGO_UX_AUDIT_USE_GATE_DB=1`** + **`DJANGO_TEST_DB_FILE`** (see `pre_deploy_gate.sh`)

## Acceptance

- [x] Install / rollback expectations documented in UI copy where applicable
- [x] Interop health surfaces reachable from operator nav where productized
- [x] **1799:** student-sheet Parent columns land in Guardians (`StudentGuardian`); post-import activate panel invites parents/teachers or issues one-time handover passwords (`bundle-activate-people`)
