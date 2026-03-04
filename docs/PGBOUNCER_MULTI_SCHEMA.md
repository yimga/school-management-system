# PgBouncer and connection pooling (multi-schema)

Optional. Part 3.4 / 4.1. Scale connection count when many tenant schemas are in use; avoid exhausting PostgreSQL connections.

## Considerations with django-tenants

- **Schema per request:** django-tenants sets `search_path` to the tenant schema for each request (via middleware). The app does not hold a long-lived session per schema.
- **Transaction mode:** With PgBouncer in **transaction** mode, the session is reset between transactions. So `search_path` must be set at the start of each request (middleware already does this). No change required if middleware runs before any DB access.
- **Session mode:** If you use PgBouncer in **session** mode, one connection is held for the whole session; `search_path` set once per request persists for that connection’s lifetime. Prefer transaction mode for higher connection reuse unless you need session-scoped state.

## Recommended settings

- **Pool size:** Size the pool so `(worker processes × max connections per worker)` does not exceed PgBouncer’s `max_client_conn`, and PgBouncer’s `pool_size` per database is enough for concurrent tenant requests. For many small tenants, a single shared pool is typical.
- **ignore_startup_parameters:** If the app sends extra startup parameters, add them to `ignore_startup_parameters` in PgBouncer so connection handoff works.
- **Database name:** Point PgBouncer at the same PostgreSQL database the app uses; django-tenants uses one database and multiple schemas, not multiple databases.

## Checklist

1. Run PgBouncer in transaction mode (or session if you understand the tradeoffs).
2. Ensure tenant resolution and middleware set `search_path` (or equivalent) at the start of each request.
3. Document pool size and any deploy-specific limits in your deployment runbook (e.g. RUNMYCAMPUS_DEPLOYMENT or equivalent).

See [OPTIONAL_DEPLOYMENT_AND_AUDIT.md](OPTIONAL_DEPLOYMENT_AND_AUDIT.md) §2.
