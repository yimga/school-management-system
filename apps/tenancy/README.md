# apps/tenancy

> The tenant isolation boundary: request context, the `school_id` pin that raw
> SQL and ORM filters are checked against, RLS-JWT binding, and the schema
> drift healer.

**Tenancy:** SHARED (public schema; this app *implements* the isolation story rather than living inside it)
**Scale:** 0 models · 0 migrations · 20 test modules · ~2.8k LOC

## What this app owns

Tenancy is the app that decides which tenant a request belongs to and then makes
it expensive to accidentally read another one. It owns four things: the
`TenantContext` attached to every request, the boundary guard that pins the
resolved `school_id` and inspects every query against it, the RLS-JWT middleware
that binds Postgres' `app.current_school_id` GUC, and `schema_repair.py` — the
healer for tenant schemas whose `school_id` columns never landed.

The defining design decision is that the platform runs **two tenancy strategies**
and `strategy.py` is the single place that says which one is live.
`SCHEMA_PER_TENANT` is django-tenants (a Postgres schema per school, resolved by
`TenantMainMiddleware`); `SHARED_SCHEMA` is one schema with Postgres `FORCE ROW
LEVEL SECURITY` policies keyed on the `app.current_school_id` GUC. `checks.py`
exists specifically to make running *both* resolution paths in one request a
startup Error, not a runtime mystery — see `tenancy.E001`/`E003`.

Under RLS mode the load-bearing isolation contract is **the database's own RLS
policies**, not application-layer `WHERE school_id=...` filters
(`middleware_rls_jwt.py`). The boundary guard is defense-in-depth on top of that,
not a replacement for it.

## Key models

**None — this app declares no Django models and ships no migrations.** That is
structural, not an omission: tenancy is a guardrail layer over *other* apps'
tables. It has nothing of its own to persist. The tenant identity itself lives on
`schools.School` (and, in schema mode, the django-tenants `Client` row); this app
only resolves, pins, and verifies it. Note the consequence for `schema_repair`:
because this app owns no migrations, the healer must be invoked from a graph-leaf
`RunPython` inside *each* tenant app (see below).

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Middleware | `TenantContextMiddleware` | Sets `request.tenant_ctx`; must run *after* tenant/school resolution |
| Middleware | `TenantBoundaryCoreGuardMiddleware` | Pins `school_id` + wraps DB executes for the request lifetime |
| Middleware | `RLSJWTBindingMiddleware` | Verifies the `rmc_rls_jwt` HS256 cookie, binds `app.current_school_id` |
| Module | `boundary_core_guard` | The pin itself: `pin_tenant_boundary`, `boundary_bypass`, execute wrapper |
| Module | `schema_repair` | `ensure_app_school_id_columns(app_label)` — idempotent missing-column heal |
| Module | `strategy` | `get_tenant_strategy()` — SCHEMA vs RLS, the single source of truth |
| Module | `checks` | Django system checks `tenancy.E001`–`E011`, `W001` |
| Module | `celery_boundary` | `@tenant_boundary_task` / `with_tenant_task_boundary` for async work |
| Module | `tasks` | `@tenant_task` — refuses to run without `schema_name` or `school_id` |
| Module | `queryset_boundary` | `scoped_queryset_for_school`, `filter_by_pinned_school` |
| Mgmt command | `verify_database_pooling` | Asserts `DB_POOL_MODE` is compatible with tenant context |

No `urls.py` — this app has no views.

### `schema_repair.ensure_app_school_id_columns`

The tenant-isolation wave retrofitted a nullable `school` FK onto many tenant-app
models. A tenant schema provisioned by **cloning a recorded migration state** —
or whose `migrate` fell short while `django_migrations` already recorded the
migration as applied — carries the record without the column ever landing. Every
ORM query then 500s with `column <table>.school_id does not exist`.

The healer introspects the **live model registry** and re-adds the `school` FK
column for every managed model in `app_label` whose current field set declares
one, but only where the column is genuinely absent. Introspection is the point:
an explicit list of models *can* miss one, an introspection pass cannot. It is a
no-op on healthy schemas and a one-shot heal on drifted ones. Currently invoked
from graph-leaf `RunPython` migrations in academics, communication, evals,
finance, people, portal, and reports.

## Before you change this

- **Middleware order is load-bearing, not stylistic.** `TenantContextMiddleware`
  must run *after* `TenantMiddleware` (RLS) or `TenantSchemaSchoolBridgeMiddleware`
  (schema) — it reads `request.school` / `request.tenant`, which those set.
  `TenantBoundaryCoreGuardMiddleware` must run after `TenantContextMiddleware`
  because it reads `request.tenant_ctx`. Reordering these silently produces an
  unpinned request (enforcement skipped) rather than an error.
- **An unpinned context skips enforcement by design.** Platform/control-plane
  requests have no `school_id` and the guard is a no-op for them. Do not "fix"
  this by pinning a default — cross-tenant management commands are supposed to
  use `boundary_bypass()` / `rls_bypass()` explicitly. The two are integrated:
  `AppConfig.ready()` calls `integrate_rls_bypass_context()` so `rls_bypass()`
  also lifts the boundary guard.
- **The RLS-JWT middleware must never raise into the request path.** A bad,
  expired, or unverifiable JWT is silent by contract — the request falls back to
  session-based binding. If you add a failure mode here that 5xxs, you have
  turned a cookie problem into an outage.
- **The host school always outranks the JWT cookie.** The cookie is host-scoped
  and only re-mints when absent, so an operator switching tenants on the shared
  manager host keeps a cookie pinned to the *first* school. The middleware
  detects divergence, binds the authoritative host school, logs
  `rls_jwt.school_divergence`, and drops the stale cookie. Do not "simplify" this
  into trusting the cookie — that silently diverges the RLS context from
  `request.school` and the DB router.
- **HSM-not-configured fails closed.** If an operator selects an HSM signing
  backend but does not wire it, verification refuses rather than falling back to
  the local key. Falling back would silently defeat the operator's HSM intent.
- **PgBouncer transaction pooling is incompatible** with the current tenant
  context and `checks.py` raises `tenancy.E009` for it. Both RLS mode
  (`app.current_school_id`) and schema mode (`search_path`) require server-session
  state. Use `DB_POOL_MODE=direct` or `session`.
- **`schema_repair` heals toward the *current* model state**, not the historical
  one, and uses a fresh `schema_editor` — that is deliberate. It is why it must
  be wrapped in a graph-**leaf** `RunPython` per tenant app: run it mid-graph and
  it heals to a field set that migration doesn't have yet. Before hand-rolling a
  new column heal, run `migrate --plan` and grep for `schema_repair` — the generic
  healer probably already covers you.
- `unpin_tenant_boundary` is token-matched: a mismatched token logs a warning and
  refuses to unpin rather than clearing someone else's pin. Keep that.
