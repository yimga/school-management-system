# Tenant isolation contract

Invariants and guarantees for multi-tenant isolation.

## Modes

- **Schema-per-tenant** (`USE_DJANGO_TENANTS=True`): Each tenant has a dedicated PostgreSQL schema. Request runs in that schema; cross-tenant reads are impossible at the DB level.
- **Single-schema RLS** (`USE_DJANGO_TENANTS=False`): One schema; RLS and `app.current_school_id` restrict rows. Unset context = deny. Bypass `app.rls_bypass = 'on'` only where explicitly used.

## Invariants

1. **Schema mode**: Request runs in tenant schema; cross-tenant data access not possible. Public schema must not contain tenant-scoped rows unless intended.
2. **RLS mode**: Request has `app.current_school_id` set (session-scoped), RESET on response/exception. Unset = default-deny (no rows). Bypass only for mgmt commands.
3. **Background jobs**: Tenant-scoped tasks run with explicit tenant identity; use TenantAwareTask or `tenant_context` / `rls_school`.

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
