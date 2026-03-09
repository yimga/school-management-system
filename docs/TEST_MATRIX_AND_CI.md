# Test Matrix and CI (Wave 7.1–7.3)

**Purpose:** Document tenant isolation test matrix, control-plane tests in CI, and lint/checks run in CI.

## 7.1 Tenant isolation test matrix

Critical flows must be validated in both tenancy modes where applicable:

| Mode | Env | Notes |
|------|-----|--------|
| `TENANCY_MODE=SCHEMA` | CI / staging | Schema-per-tenant; connection routing. |
| `TENANCY_MODE=RLS` | CI / staging | Row-level security; single schema. |

**Flows to run in both modes (when both are supported):**

- Control-plane boundary: manager host denies tenant staff for `/super/`, `/api/search/` (Wave 1).
- Tenant admin: tenant URLConf serves `/admin/` with tenant admin site (Wave 2).
- GraphQL: tenant staff gets `schoolCount: null`, `schools: []` (Wave 2).
- Tenant-scoped list views: e.g. requests, finance, evals filtered by current school (Wave 4).

**CI recommendation:** Run the Wave 1–4 test modules under one tenancy mode by default; add a second CI job with the other mode when both are in use, or document “RLS matrix run” as a manual/release checklist.

## 7.2 Control-plane and Wave tests in CI

The following test modules are non-negotiable and should run in CI:

- `apps.schools.tests.test_control_plane_boundary`
- `apps.tenancy.tests.test_manager_urlconf_boundary`
- `apps.schools.tests.test_wave2_admin_and_graphql`
- `apps.schools.tests.test_wave3_superadmin_dashboard`
- `apps.schools.tests.test_wave4_tenant_scoping`
- `apps.schools.tests.test_wave5_config_canonical`

**Example:**

```bash
python manage.py test apps.schools.tests.test_control_plane_boundary apps.tenancy.tests.test_manager_urlconf_boundary apps.schools.tests.test_wave2_admin_and_graphql apps.schools.tests.test_wave3_superadmin_dashboard apps.schools.tests.test_wave4_tenant_scoping apps.schools.tests.test_wave5_config_canonical --keepdb
```

Or with pytest:

```bash
pytest apps/schools/tests/test_control_plane_boundary.py apps/tenancy/tests/test_manager_urlconf_boundary.py apps/schools/tests/test_wave2_admin_and_graphql.py apps/schools/tests/test_wave3_superadmin_dashboard.py apps/schools/tests/test_wave4_tenant_scoping.py apps/schools/tests/test_wave5_config_canonical.py -v --reuse-db
```

## 7.3 get_solo and tenant-scoping lints in CI

- **get_solo lint:** `python scripts/lint_tenant_settings.py --check-get-solo-only`  
  - Ensures tenant apps use get_solo with a school/tenant scope where required.  
  - See `apps/platform_runtime/tests/test_tenant_settings_lint.py`.

- **Tenant cache prefix lint:** `python scripts/lint_tenant_cache_prefix.py`  
  - Fails if tenant app code uses `get_tenant_cache_prefix(None)` outside allowlist.  
  - Use `--exit-zero` only for a “report only” CI step until call sites are fixed.

**Recommendation:** Run both lints in CI; fix or allowlist any reported call sites so the cache lint exits 0.
