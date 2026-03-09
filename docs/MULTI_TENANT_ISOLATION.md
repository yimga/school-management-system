# Multi-tenant isolation and runtime-only

**Goal:** No backward-compatibility fallbacks in tenant request path; tenant-scoped data everywhere; provisioning automated and tested; isolation tests for tenant apps.

## Rules

1. **Runtime only:** Tenant behavior comes from `request.tenant_runtime` and tenant context (`request.school`, `request.tenant_ctx`). No "if no runtime then use X" in tenant views or services.
2. **Tenant-scoped queries:** All tenant app models must filter by school_id or schema_name (tenant_id). No cross-tenant reads or writes.
3. **Provisioning:** New tenants via control-plane (create school wizard, API) or signup; use `ensure_default_tenant_admin` and migrations. Document in runbooks.
4. **Control-plane vs tenant:** Manager host serves only control-plane and public routes; tenant host serves tenant app routes. No `/super/` on tenant URLconf. See docs/CONTROL_PLANE_BOUNDARY_RULES.md.

## Isolation tests

- **Existing:** `apps/schools/tests/test_control_plane_boundary.py`, `test_phase10_control_plane_verification.py`, `apps/tenancy/tests/test_manager_urlconf_boundary.py` — tenant cannot resolve `/super/`; manager host denies non–platform users.
- **Per-tenant data:** Add or extend tests that create data as tenant A and assert tenant B (or unauthenticated) cannot read/update it for critical models (e.g. evals, finance, people). Use tenant-specific client or schema switch.

## Fallbacks

- Any fallback that bypasses runtime (e.g. direct SiteSettings or first school) must be allowlisted and documented. Lint and tests enforce no new tenant-path bypasses.

## References

- apps/tenancy/middleware.py — tenant resolution
- apps/platform_runtime/middleware.py — runtime on request
- docs/PLATFORM_APPS_PUBLIC_API.md (tenancy section)
