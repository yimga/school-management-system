# Permissions and scope (Phase 10)

**Goal:** Align permissions with multitenant isolation; every workflow and metadata resolution is tenant-aware; scope is explicit; governor limits are defined and enforced.

## 5.1 Tenant context everywhere

- **Request:** Every relevant request carries tenant context (TenantContextMiddleware, request.tenant_ctx, request.school).
- **Events:** Every event carries tenant context where applicable (school_id / tenant in payload; event catalog).
- **Workflow runs:** Every workflow run must be tenant-scoped (school_id in execution context; AutomationExecutionLog scoped by tenant).
- **Metadata resolution:** Runtime resolution is tenant-aware (RuntimeResolver builds per tenant_ctx + school; blueprint, policy, entitlements per school).
- **Cache keys:** Cache keys include tenant where dependent (platform_runtime/cache.py: `tenant_runtime_cache_key(school_id, segment)`, `_request_cache_key(tenant_ctx, school)`).

## 5.2 Scope modeling

Every metadata item should declare scope. Allowed values:

| Scope | Meaning |
|-------|--------|
| **platform** | Global; all tenants; e.g. country registry, default blueprint list |
| **regional** | Per region/country; e.g. RegionalConfig, locale packs |
| **blueprint** | Per blueprint; e.g. blueprint-specific workflow/dashboard packs |
| **pack** | Per workflow/dashboard/policy pack; versioned, installable |
| **tenant** | Per school/tenant; overrides, branding, installed packs |
| **sandbox** | Sandbox/preview tenant; no production data |

Documentation: bounded_contexts.md, central_metadata_catalog.md, siteconfig_decomposition.md. Implement scope on new metadata; backfill on existing where needed.

## 5.3 Tenant isolation

- **Tests:** Verify tenant metadata cannot leak (test_control_plane_boundary, RLS where applicable).
- **Overrides:** Tenant overrides must not mutate platform defaults (copy-on-write or overlay; runtime compiles per tenant).
- **Cache:** Cached runtime is keyed by tenant; invalidate_tenant_runtime_cache(school_id) on config change.

## 5.4 Governor limits

Defined in `apps/platform_runtime/governor_limits.py` and overridable via `settings.PLATFORM_GOVERNOR_LIMITS`:

- workflow_runs_per_tenant_per_hour
- api_requests_per_minute_per_tenant
- migration_concurrent_runs
- bulk_export_max_rows
- ai_invocations_per_tenant_per_day
- dynamic_fields_per_entity
- pack_dependency_depth

Enforce in workflow engine, API throttling, migration runner, and pack install where applicable.
