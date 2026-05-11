# Tenant isolation contract

Invariants and guarantees for multi-tenant isolation.

## Modes

- **Schema-per-tenant** (`USE_DJANGO_TENANTS=True`): Each tenant has a dedicated PostgreSQL schema. Request runs in that schema; cross-tenant reads are impossible at the DB level.
- **Single-schema RLS** (`USE_DJANGO_TENANTS=False`): One schema; RLS and `app.current_school_id` restrict rows. Unset context = deny. Bypass `app.rls_bypass = 'on'` only where explicitly used.

## Invariants

1. **Schema mode**: Request runs in tenant schema; cross-tenant data access not possible. Public schema must not contain tenant-scoped rows unless intended.
2. **RLS mode**: Request has `app.current_school_id` set (session-scoped), RESET on response/exception. Unset = default-deny (no rows). Bypass only for mgmt commands.
3. **Background jobs**: Tenant-scoped tasks run with explicit tenant identity; use TenantAwareTask or `tenant_context` / `rls_school`.
4. **RLS mode FORCE**: Every RLS-enabled tenant-scoped table runs with `FORCE ROW LEVEL SECURITY` (schools migration `0048_force_rls_on_all_enabled_tables`). Without this, the table owner bypasses every policy — so the policies bind for nobody in practice. Any code path that runs as the owner role and needs cross-tenant access MUST wrap in `rls_bypass()`; otherwise it will hit default-deny.

## Threat model

- Cross-tenant data leak (user A must not see B data).
- Accidental public-schema tenant query in schema mode.
- RLS context leak (connection reuse without RESET); mitigated by middleware RESET.

## Checklist

- USE_DJANGO_TENANTS and DB engine consistent (compliance.E001/E002).
- Schema mode: RLS not enabled on tenant schemas (gated migrations).
- RLS mode: SET + RESET in middleware and on exception.
- RLS mode: policies default-deny + bypass.
- Tenant-scoped Celery tasks use explicit context.
- Tests: tag `tenants_schema`, `tenants_rls`.

## CI gates

| Tag | Workflow | DB | Mode |
| --- | --- | --- | --- |
| (untagged) | `django-tests.yml` | SQLite | default |
| `tenants_schema` | `playwright-tenant-postgres.yml` | Postgres | `USE_DJANGO_TENANTS=1` |
| `tenants_rls` | `tenants-rls.yml` | Postgres | `USE_DJANGO_TENANTS=0` (single-schema RLS) |

Any test that asserts cross-tenant isolation behaviour at the DB layer **must** carry one of the two
mode tags so it runs in the correct gate. Untagged isolation tests run only on SQLite, where neither
schema separation nor RLS policies exist — they verify ORM-filter discipline only.
