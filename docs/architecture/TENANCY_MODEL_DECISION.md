# Tenancy model: schema-per-tenant primary, RLS/session secondary

**Status:** Decision recorded  
**Ref:** RunMyCampus Consolidated Architecture; `docs/architecture/tenancy.md`

## Split-brain warning

**Do not mix two tenancy models in the same request path.** Schema-per-tenant and RLS/session-variable usage must not coexist as competing sources of tenant identity. Use one mode per deployment (TENANCY_MODE); tenant always comes from **host resolution** → `request.tenant` or `request.school`. Session variables (`app.current_school_id` etc.) are for **audit and RLS scoping only**, not for resolving “which tenant am I?” in application code. See rule 24.10 and `tenancy.md`.

## Primary model: schema-per-tenant

- **Schema-per-tenant is the primary tenancy model** for RunMyCampus when multi-tenant scale and isolation are required.
- With `USE_DJANGO_TENANTS=1`:
  - Each tenant has a dedicated PostgreSQL schema (`tenant.schema_name`).
  - `django_tenants.middleware.main.TenantMainMiddleware` resolves `request.tenant` from host and sets the DB connection to that schema for the request.
  - `TenantSchemaSchoolBridgeMiddleware` sets `request.school` from `tenant.school`.
  - Tenant identity and data isolation are enforced by schema boundaries; no row-level predicates are required for tenant scoping within the schema.

## Secondary / transitional: RLS and session variables

- **RLS (row-level security)** with `USE_DJANGO_TENANTS=0` is a **secondary model** for single-schema deployments (e.g. small or single-tenant).
  - `request.school` is set by host via `TenantMiddleware`; `app.current_school_id` (or equivalent session variable) is set for RLS policies to filter rows.
- **Session variables** (e.g. `app.current_school_id`) are **not** the source of tenant identity for application logic.
  - They are used only for:
    - **Audit/request context** (who/what/where in logs and audit records).
    - **RLS scoping** when in RLS mode (PostgreSQL policies filter by the session variable).
  - Application code must **not** resolve tenant from session variables; tenant comes from **host resolution** and `request.school` / `request.tenant` only. See non-negotiable rule 24.10 and `tenancy.md`.

## Where tenant is set (recap)

| Mode              | Tenant set by                                      | DB scope                          |
|-------------------|----------------------------------------------------|-----------------------------------|
| Schema-per-tenant | `TenantMainMiddleware` → `request.tenant`; bridge → `request.school` | Connection schema = `tenant.schema_name` |
| RLS               | `TenantMiddleware` → `request.school`; RLS uses `app.current_school_id` | Single schema; RLS filters by school_id |

## Application contract

- **Single entry point for tenant context:** `request.tenant_ctx` (TenantContext) and `request.tenant_runtime` (TenantRuntime).
- **Policy and behavior:** Use `request.tenant_runtime.policy` (or `get_effective_policy(school)` where runtime is not yet used); do not read `School.settings` / `School.features` directly in app code.
- **Schema vs RLS:** New code and migrations should assume schema-per-tenant as the target; RLS/session usage is transitional and documented where applied (e.g. `RlsResetOnExceptionMiddleware`, `app.current_school_id` in RLS policies).

## References

- `docs/architecture/tenancy.md` — Modes, where tenant is set, schema switching, shared vs tenant tables.
- `docs/architecture/request_flow_tenant_resolution.mmd` — Request flow and tenant resolution.
- `apps/tenancy/context.py` — TenantContext.
- `apps/platform_runtime/` — TenantRuntime and `request.tenant_runtime`.
