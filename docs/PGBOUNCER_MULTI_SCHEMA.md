# PgBouncer and tenant context

Optional connection-scaling guidance for both supported tenancy profiles:
django-tenants schema isolation and single-schema PostgreSQL RLS.

## Current production decision

Use a PostgreSQL **session-pooling or unpooled endpoint**. Do not use PgBouncer
transaction pooling with the current tenant-context implementation.

The reason is structural:

- django-tenants selects a tenant with session state such as `search_path`.
- RLS mode selects a tenant with session-level
  `SET app.current_school_id = ...` and resets it after the request.
- PgBouncer documents `SET` / `RESET` session state as unsupported in
  transaction pooling because the next transaction may use a different server
  connection.

Setting tenant state once at request start is therefore insufficient when a
request can contain multiple autocommit transactions.

Upstream feature matrix: <https://www.pgbouncer.org/features.html>

## Safe current configuration

1. Point `DATABASE_URL` at the provider's direct or session-pooling endpoint.
2. Set `DB_POOL_MODE=direct` for an unpooled endpoint or
   `DB_POOL_MODE=session` for PgBouncer session pooling. Django system checks
   reject `transaction` on PostgreSQL.
3. Keep tenant middleware before tenant-scoped database access.
4. Keep `DB_CONN_MAX_AGE` aligned with the provider's session-pool guidance.
5. Set `DB_DISABLE_SERVER_SIDE_CURSORS=1` only when required by the selected
   pooler/provider mode.
6. Size the pool from measured concurrent requests and database connection
   limits. Do not use an assumed latency target as the sizing rule.
7. Verify schema/RLS isolation through the same endpoint used in production.

If an RLS request/task cannot reset `app.current_school_id` or
`app.rls_bypass`, RunMyCampus closes that database connection so stale tenant
session state cannot return to Django or a session pool.

Pre-deploy checks:

```bash
python manage.py verify_database_pooling
python manage.py check
npm run verify:database-tenancy
```

## Transaction-pooling enablement gate

Transaction pooling remains a future optimization, not an approved deployment
profile. Before enabling it:

1. Bind schema or RLS context inside the same database transaction as every
   tenant query, using transaction-local state where applicable.
2. Define request-wide transaction behavior and explicitly handle streaming
   responses, nested atomics, non-atomic views, Celery tasks, management
   commands, background workers, and exception paths.
3. Keep default-deny RLS and `FORCE ROW LEVEL SECURITY`; do not replace the
   canonical `app.current_school_id` contract with a second GUC.
4. Add integration tests against real PostgreSQL plus PgBouncer transaction
   mode. Interleave two tenants across reused server connections and prove no
   stale, unset, or cross-tenant context.
5. Load-test throughput and connection pressure before and after the change.

Only after those gates pass may transaction pooling be documented as supported.

See [OPTIONAL_DEPLOYMENT_AND_AUDIT.md](OPTIONAL_DEPLOYMENT_AND_AUDIT.md) and
[AI_DEPLOYMENT_POSTURE.md](AI_DEPLOYMENT_POSTURE.md#research-re-audit-addendum-2026-06-08).
