# Tenancy

Where tenant is set, schema switching, and shared vs tenant tables (RunMyCampus blueprint).

## Modes

- **RLS (row-level security):** `USE_DJANGO_TENANTS=0`. Single schema; tenant = school; `request.school` set by host. Row-level security and `app.current_school_id` scope tenant data.
- **Schema-per-tenant:** `USE_DJANGO_TENANTS=1`. `django-tenants`; `request.tenant` is `Client`; `request.school` from tenant’s linked School. Each tenant has its own PostgreSQL schema.

## Where tenant is set

1. **RLS mode**
   - `apps.schools.middleware.TenantMiddleware`: resolves `request.school` from host (subdomain or `X-Tenant-Slug` etc.).
   - `apps.schools.middleware.RlsResetOnExceptionMiddleware`: resets `app.current_school_id` on response/exception so RLS is scoped per request.

2. **Schema-per-tenant mode**
   - `django_tenants.middleware.main.TenantMainMiddleware`: resolves `request.tenant` from host and switches DB connection to tenant schema.
   - `apps.schools.middleware.TenantSchemaSchoolBridgeMiddleware`: sets `request.school` from `tenant.school`.
   - `apps.schools.middleware.TenantSchoolNotFoundMiddleware`: handles missing tenant/school.

3. **Tenant context (both modes)**
   - `apps.tenancy.middleware.TenantContextMiddleware`: builds `request.tenant_ctx` (TenantContext) from `request.school` or `request.tenant`. Runs after tenant/school resolution. Does **not** read/write DB schema; only attaches context (tenant_id, schema_name, school_id, country, timezone, feature_flags, policy_overrides, host).

4. **Session variables (PostgreSQL)**  
   `app.current_school_id` (and any `app.*` session vars) are used **only for audit/request context and RLS scoping** — not as a second tenancy model. Tenant identity comes from host resolution and `request.school` / `request.tenant`; session vars must not be used to resolve tenant in application code. See non-negotiable rule 24.10.

## Schema switching

- **RLS:** No schema switch; connection stays on default schema. `set_config('app.current_school_id', school_id)` (or equivalent) is applied so RLS policies filter by school.
- **Schema-per-tenant:** `TenantMainMiddleware` sets the connection’s `schema_name` to `tenant.schema_name` for the request. All ORM queries in that request run in the tenant’s schema unless explicitly using a shared app.

## Shared vs tenant tables

- **Shared (public schema in schema-per-tenant):** Typically `customers.Client`, `customers.Domain`, and any app in `SHARED_APPS` in django-tenants settings. Used for tenant resolution and platform-wide data.
- **Tenant tables:** All other project apps (accounts, schools, academics, people, finance, etc.) live in the tenant schema in schema-per-tenant mode, or in the single schema with RLS in RLS mode. RLS policies restrict rows by `school_id` (or equivalent) when in RLS mode.

## Multi-DB routing (data sovereignty / scale)

- **School.regional_cluster:** Optional region label (e.g. `eu`, `apac`) for routing; can be used as DB alias when `DATABASES` has matching keys.
- **School.dedicated_db_alias:** Optional dedicated DB alias for mega-schools (10k+ students). When set and present in `DATABASES`, tenant reads/writes for that school use that alias.
- **TenantDatabaseRouter** (`apps.siteconfig.db_router`): When `connection.tenant` is set (schema-per-tenant), uses `tenant.db_alias`, then `tenant.school.dedicated_db_alias`, then `tenant.school.regional_cluster` to choose DB. When `DATABASE_READ_REPLICA_ALIAS` is set, read queries use the replica; writes use the tenant’s primary alias.
- **RLS mode:** Single DB; router does not switch. For future multi-DB in RLS, a separate mechanism (e.g. thread-local current school + router) would be needed.

## Configuration

- `config/settings.py`: `ROOT_URLCONF`, `PUBLIC_SCHEMA_URLCONF`, `TENANT_SCHEMA_URLCONF`, `TENANT_MODEL`, `TENANT_DOMAIN_MODEL`, `DATABASE_ROUTERS`, `DATABASE_READ_REPLICA_ALIAS` (optional).
- `apps.tenancy`: `TenantContext`, middleware, `@tenant_task` and tenant checks (E001–E003) for background tasks.
- `apps.schools.tenant_url`: host → school resolution, base domain detection, single-tenant slug.
