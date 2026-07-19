# apps/customers

> The django-tenants tenant registry: which schools exist as tenants, which
> PostgreSQL schema each one owns, and which hostname resolves to which.

**Tenancy:** SHARED (public schema — and it could not be anything else; see below)
**Scale:** 2 models · 4 migrations · 1 test module · ~0.6k LOC

## What this app owns

This app is the root of the platform's multi-tenancy topology. `config/settings.py`
names its two models as the django-tenants contract:

```python
TENANT_MODEL = "customers.Client"          # settings.py:527 and :3865
TENANT_DOMAIN_MODEL = "customers.Domain"   # settings.py:528 and :3866
```

Every request that resolves to a tenant subdomain does so by matching the `Host`
header against a `Domain` row, which points at a `Client`, whose `schema_name` is
the PostgreSQL schema `SET search_path` then selects. `Client` carries a
`OneToOneField` to `schools.School`, so `request.tenant.school` hands the rest of
the platform the School record it already understands — `Client` is the *schema*
identity, `School` is the *business* identity, and the OneToOne is the seam
between them.

The reason this app lives in `SHARED_APPS` (public schema) is structural, not a
preference: the tenant registry has to be readable *before* a schema can be
chosen. If `customers_client` lived inside a tenant schema, resolving which
schema to use would require already knowing which schema to use.

The platform has **two mutually exclusive tenancy modes**, and this app is only
load-bearing in one of them (`config/settings.py:3829-3852`):

| Mode | `TENANCY_MODE` | How the tenant is resolved |
| --- | --- | --- |
| Schema-per-tenant | `SCHEMA` (`USE_DJANGO_TENANTS=1`; the default on PostgreSQL) | `HealthAwareTenantMainMiddleware` → `Domain` → `Client` → schema; then `TenantSchemaSchoolBridgeMiddleware` sets `request.school` |
| Shared table + RLS | `RLS` (`USE_DJANGO_TENANTS=0`, or any non-PostgreSQL engine) | `apps.schools.middleware.TenantMiddleware` resolves `request.school` from School/SchoolDomain/subdomain. `Client` and `Domain` rows are inert |

## Key models

Both models are thin subclasses of the django-tenants mixins — the framework
supplies `schema_name`, `domain`, `tenant`, and `is_primary`; this app adds the
platform-specific fields.

| Role | Model | Table | Purpose |
| --- | --- | --- | --- |
| Tenant | `Client` (`TenantMixin`) | `customers_client` | One row per tenant school. Owns `schema_name` (normalized from `School.slug`), the `school` OneToOne into the public schema, and `db_alias` |
| Domain | `Domain` (`DomainMixin`) | `customers_domain` | Hostname → tenant map. Subdomain or custom domain; `is_primary` picks the canonical one |

`Client.db_alias` is the World Engine hook: when set (e.g. `region_eu`,
`dedicated_xyz`), `apps.siteconfig.db_router.TenantDatabaseRouter` routes that
tenant's queries to a different database alias entirely. Blank means the default
database.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Management command | `ensure_tenant_schemas` | Creates missing PostgreSQL schemas for existing Clients. `--dry-run` supported. No-op on non-PostgreSQL and when `USE_DJANGO_TENANTS` is false |
| Module | `repositories/schema_provisioning_repository` | The only place that provisions a schema: `schema_exists()` / `create_schema_if_not_exists()` |
| Admin | `ClientAdmin` (via `TenantAdminMixin`), `DomainAdmin` | Registered in `admin.py` |

This app exposes no URLs of its own (no `urls.py`) and no Celery tasks. It is a
registry that middleware reads, not a surface users visit.

## Before you change this

- **`auto_drop_schema = False` is a deliberate safety rail.** `auto_create_schema`
  is `True`, so creating a `Client` provisions its schema — but deleting a
  `Client` does **not** drop the PostgreSQL schema, and the tenant's data
  survives the row. This asymmetry is intentional: an accidental `Client.delete()`
  (or a cascade from `School`, which is `on_delete=CASCADE`) must never be a
  one-statement data loss event. Dropping a schema is an explicit, deliberate
  operator act. Do not "fix" the asymmetry.
- **`ensure_tenant_schemas` exists because `auto_create_schema` has a hole.**
  When a `Client` is created *inside a migration* (as customers migration
  `0003` — legacy default-tenant domain ensure — does), django-tenants' auto-create hook may not fire, and the later
  `migrate_schemas --tenant` dies with `"no schema has been selected to create in"`.
  The command's ordering contract is therefore: `migrate_schemas --shared` →
  `ensure_tenant_schemas` → `migrate_schemas --tenant`. Creating a Client in a
  migration without honouring that order re-opens the bug.
- **All schema DDL goes through the repository, and it validates the name first.**
  `_normalize_schema_name()` rejects non-strings, `bool`, `bytes`, `Mapping`, and
  anything failing `^[A-Za-z_][A-Za-z0-9_]{0,62}$` before a schema name reaches
  the database — a schema name is an SQL identifier that cannot be parameterized,
  so the allowlist regex *is* the injection defense. Do not build a `CREATE SCHEMA`
  string anywhere else.
- **`TENANT_MODEL` / `TENANT_DOMAIN_MODEL` are declared unconditionally at
  `settings.py:527`, outside the `USE_DJANGO_TENANTS` branch, on purpose.** The
  in-repo comment states why: "some background integrations import django-tenants
  helpers unconditionally." Seeing those settings defined does **not** mean
  schema-per-tenant is active — check `USE_DJANGO_TENANTS` / `TENANCY_MODE`, not
  the presence of `TENANT_MODEL`.
- **`Client.school` is nullable.** `null=True, blank=True` — a `Client` can exist
  with no `School` attached. Code doing `client.school.<anything>` must handle
  `None`.
- **The repository no-ops on non-PostgreSQL rather than raising.** `schema_exists()`
  returns `False` and `create_schema_if_not_exists()` returns silently when
  `connection.vendor != "postgresql"`, so the SQLite test path stays green. A
  `False` from `schema_exists()` therefore means "absent *or* not applicable" —
  never read it as proof a schema is missing without checking the vendor.
- **`SHOW_PUBLIC_IF_NO_TENANT_FOUND = True`** (`settings.py:3867`): an unmatched
  hostname falls through to the public schema instead of raising. A "why is my
  tenant showing the marketing site" report usually means a missing `Domain` row,
  not a broken view.
