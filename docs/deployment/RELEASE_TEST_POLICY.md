# Release test policy (RunMyCampus) — **LOCKED STABLE**

**Purpose:** Definitive **go/no-go** for production cutover, enterprise demos, and scaling after stabilization. The engineering ledger in `docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md` still governs batch work; this file is the **release gate** for “safe to deploy / demo / sell / scale”.

## RELEASE GREEN = **all** of the following

### 1. Full Django test suite (required)

- `python manage.py test --noinput` completes with **0 failures** (skips are allowed if intentional).
- **Fresh DB** proof on CI or a clean agent (avoids false greens from a stale `DJANGO_TEST_DB_FILE`):

```text
rm -f .django_test_dbs/final_lock.sqlite3
DJANGO_TEST_DB_FILE=.django_test_dbs/final_lock.sqlite3 python manage.py test --noinput
```

On **Windows**, a brand-new file-backed test database can be slow; **CI Linux** is the source of truth for the fresh-DB line above. If local runs are impractical, do not claim green from a partial list alone.

**Environment-only** failures (e.g. worker OOM, disk full, wrong Python, broken `DJANGO_SETTINGS_MODULE`) are **not** product regressions — retry or fix the runner, then re-run.

### 2. Required verifier bundle (mechanical, required)

All **exit 0** (no flags loosened):

- `python scripts/audit_admin_gravity.py --strict`
- `python scripts/verify_shell_surface_inventory.py`
- `python scripts/verify_phase2_authenticated_shell_conformance.py`
- `python scripts/verify_design_system_phase2.py`
- `python scripts/verify_doc_plan_density_discipline.py`
- `python scripts/verify_sot_pillar_evidence.py`
- `python scripts/audit_sitesettings_python_surface.py`
- `python scripts/verify_cursor_phase6_siteconfig_sitesettings.py`

### 3. i18n catalog discipline (when shipping UI strings)

- `python scripts/verify_i18n_catalog_fresh.py` — run before release if templates/messages changed in the cut.

**Optional** scripts (lint-only, inventory cadence, experimental gates) **do not** block **RELEASE GREEN** unless a release note or SOT row explicitly elevates them for that cut.

### 4. Manual — not automated

- Execute **`docs/deployment/LAUNCH_SMOKE_TEST.md`** on a real school host and test user; record the outcome.

## Regression coverage (pointers)

Automated guards for previously fragile areas include (non-exhaustive):

- `apps/portal/tests/test_pass_mark_regression.py` — blank/invalid `pass_mark` coercion; empty performance shell.
- `apps/sales/tests/test_pipeline.py` — `PipelineStage` presence, superuser access, idempotent seed.
- `apps/platform_runtime/tests/test_marketplace_integration_helper_contract.py` — SiteSettings singleton + integration keys.
- `apps/siteconfig/tests/test_*_setup_evidence.py` — `reverse(..., urlconf="config.tenant_urls")`, CP-before-admin ordering, non–superuser hides admin.
- `apps/tenancy/tests/test_manager_urlconf_boundary.py` — manager `/api/search/` empty-`q` full catalog (no static truncation).

## Related

- `PRODUCTION_DEPLOYMENT_CHECKLIST.md` — order of operations.
- `STAGING_RELEASE_EXECUTION.md` — predeploy → start → health → smoke.
- `DEPLOYMENT_ROLLBACK.md` — if a gate fails after deploy.
- `RELEASE_NOTES_LAUNCH.md` — operator-facing summary.
