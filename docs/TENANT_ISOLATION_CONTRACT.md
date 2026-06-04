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

## WebSocket ingress (batch 1607)

- ASGI stack: `AuthMiddlewareStack(TenantChannelsMiddleware(URLRouter(...)))` in `config/asgi.py`.
- `apps/schools/channels_tenant_middleware.py` resolves `scope["school"]` from the WS `Host` header and rejects session/JWT values that disagree with the host-resolved tenant.
- Legacy sync consumers (`apps/api/consumers.py`) and WAL ingest (`apps/wal_stream/consumers.py`) require `scope["school_id"]` and scoped channel group names (`{prefix}_{school_id}_{user_id}`).
- Gate: `python scripts/verify_websocket_tenant_scope.py` → **WEBSOCKET_TENANT_SCOPE_PASS**.

## SSE ingress (batch 1610)

- Tenant workflow progress SSE (`apps/platform_runtime/views_workflow_progress.py::stream_view`) resolves tenant schema via `_resolve_scope(request)` and returns **403** when the caller is on a tenant host without `request.school` or tenant schema.
- Portal AI stream (`apps/portal/views_ai_stream.py`) requires `request.school` on tenant hosts before streaming.
- Operator-only SSE (migration cloud progress via `_tenant_scoped_bundle`, schoolops email health) must remain on manager host with control-plane RBAC; portal shell bundles are scoped to `request.school`.
- HTTP tenant guards (`apps/schools/tenant_api_guards.py`) gate staff bypass to manager/local control-plane hosts only.

## Celery background jobs (batch 1610 / 1615)

- Tenant-scoped `@shared_task` handlers that query ORM must pass explicit `school=` / `school_id=` filters or carry a quality `# tenant-isolation-allow:` marker on the queryset line.
- Platform-wide beat tasks (cross-tenant operator metrics, upstream watches) are allowed only with documented allow markers.
- Gate: `python scripts/audit_celery_tenant_task_scoping.py --compare` → baseline **0** undocumented cross-tenant queryset sites in task modules.

## Production isolation mode

Render/production default: **schema-per-tenant** when `USE_DJANGO_TENANTS=1`; local SQLite CI uses ORM discipline + guard modules. Postgres RLS proofs run in `tenants-rls.yml` for single-schema deployments.
