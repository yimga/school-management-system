# Phase 7 verification checklist

**Status:** Verified and CI-enforced. All Phase 7 docs exist and the regression/automation suite is run in CI.

## Docs verified present

| Doc | Purpose | CI / enforcement |
|-----|---------|------------------|
| **docs/qa.md** | Phase 7 QA guide: regression focus, security/accessibility, test_core_workflows, check_api_health, CI snippet | Referenced by this checklist; commands run in gate |
| **docs/urls.md** | Phase 7 URL cleanup: semantic endpoints, breadcrumbs, redirect map | Doc present; route changes should update this |
| **docs/ux.md** | Phase 7 UX & dashboard guide: widgets, layout, accessibility, run_phase7_checks | Doc present; validation via check/test in gate |
| **docs/automation.md** | Phase 7 automation: run_phase7_checks, schedule, cleanup, threat detection | Doc present; run_phase7_checks for nightly/local |

## CI enforcement

- **scripts/pre_deploy_gate.sh** (run by `.github/workflows/smoke.yml` on push/PR to `main`):
  - `python manage.py check`
  - `python manage.py makemigrations --check --dry-run`
  - `python manage.py audit_tenant_models --strict`
  - Smoke URLs, theme matrix, phase checks (admin UI smoke, dashboard API RBAC)
  - **Phase 7:** `python manage.py test_core_workflows` (core workflow regression from `apps.siteconfig.tests.test_phase7_regression`)
  - Multi-tenant coverage tests

- **Nightly / local:** Run `python manage.py run_phase7_checks` (and optionally `check_api_health`) as in docs/qa.md and docs/automation.md.

## Verification date

- Phase 7 docs and regression suite verified and wired into CI as of this checklist.
- Last updated: 2026-03 (roadmap completion pass).
