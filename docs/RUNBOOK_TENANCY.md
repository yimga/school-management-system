# Runbook: Tenancy

Operations guide for creating tenants, running migrations, and troubleshooting tenant isolation.

## Creating a tenant

### Schema-per-tenant (`USE_DJANGO_TENANTS=True`)

1. Create a **Client** (tenant) and **Domain** in the public schema (e.g. via Django admin or shell).
2. Run tenant migrations so the tenant schema has all tables:
   ```bash
   python manage.py migrate_schemas --shared   # if shared schema changed
   python manage.py migrate_schemas --tenant   # all tenant schemas
   ```
3. Optionally create a **School** row inside that tenant's schema (if your flow creates School per tenant).

### Single-schema RLS (`USE_DJANGO_TENANTS=False`)

1. Create a **School** row (and any host/subdomain mapping, e.g. **SchoolDomain**).
2. Ensure the host is resolved by **TenantMiddleware** (subdomain or custom domain). No separate Client/Domain.
3. Run standard migrations (no `migrate_schemas`):
   ```bash
   python manage.py migrate
   ```

## Running migrations

| Mode              | Command                                      | Notes |
|-------------------|-----------------------------------------------|--------|
| Schema-per-tenant| `migrate_schemas --shared` then `--tenant`   | Shared tables in public; tenant tables per schema. |
| RLS (single-schema) | `migrate`                                 | All tables in default schema; RLS enabled only when `USE_DJANGO_TENANTS=False`. |

When `USE_DJANGO_TENANTS=True`, RLS enable migrations no-op on tenant schemas (gated by `should_apply_rls(connection)`).

## Troubleshooting

1. **Check tenancy mode**
   - `USE_DJANGO_TENANTS=1` → schema-per-tenant (PostgreSQL + `django_tenants.postgresql_backend` required).
   - `USE_DJANGO_TENANTS=0` or unset → single-schema with RLS (PostgreSQL).

2. **Check current schema (schema mode)**
   - In Django shell or logs, ensure the request or task runs inside `tenant_context(client)` so `connection.tenant` is set.
   - Raw SQL: `SELECT current_schema();`

3. **Check GUC (RLS mode)**
   - In a DB session: `SELECT current_setting('app.current_school_id', true);`
   - Expect a school UUID when handling a tenant request; empty after RESET.
   - For bypass: `current_setting('app.rls_bypass', true) = 'on'` only when explicitly set (e.g. management command using `rls_bypass()`).

4. **Django system checks**
   - Run `python manage.py check`. If `USE_DJANGO_TENANTS` is True but the default DB engine is not `django_tenants.postgresql_backend`, you get `compliance.E002`.

## Running isolation tests locally

- **Schema mode** (PostgreSQL + `USE_DJANGO_TENANTS=1`):
  ```bash
  USE_DJANGO_TENANTS=1 python manage.py test --tag=tenants_schema
  ```
- **RLS mode** (PostgreSQL + `USE_DJANGO_TENANTS=0`):
  ```bash
  USE_DJANGO_TENANTS=0 python manage.py test --tag=tenants_rls
  ```

On SQLite, both suites are skipped (they require PostgreSQL). In CI, run both when the test DB is PostgreSQL; document the above commands for local runs.
