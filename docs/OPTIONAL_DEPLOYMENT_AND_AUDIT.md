# Deployment and audit hardening

Optional items from RUNMYCAMPUS_SINGLE_PLAN_COMPLETE (Part 3.4 / 4.x). Primary isolation remains **schema-per-tenant**; these are defense-in-depth or operational improvements.

## 1. RLS (Row-Level Security) on tenant tables

- **Purpose:** Defense-in-depth only. Do **not** rely on RLS for tenant isolation; schema is the single source of truth.
- **How:** For each tenant schema, enable RLS on key tables and add a policy that restricts rows by a stable tenant identifier (e.g. `current_setting('app.current_schema') = current_schema()`). Ensure the app sets the same before queries.
- **Example (per tenant schema):**
  ```sql
  ALTER TABLE people_studentprofile ENABLE ROW LEVEL SECURITY;
  CREATE POLICY tenant_isolation ON people_studentprofile
    USING (current_schema() = current_setting('app.current_schema', true));
  ```
- **Status:** Implemented through reviewed migrations and the canonical
  `app.current_school_id` context contract. Schema-per-tenant remains primary.

## 2. PgBouncer and connection pooling (multi-schema)

- **Purpose:** Scale connection count when many tenant schemas are in use; avoid exhausting PostgreSQL connections.
- **Current contract:** Use a direct endpoint or PgBouncer **session mode** and
  declare it with `DB_POOL_MODE=direct|session`. Both django-tenants
  `search_path` and shared-schema RLS `app.current_school_id` are session state.
  Request-start binding is not sufficient for transaction pooling because one
  request can issue multiple autocommit transactions on different server
  connections. `DB_POOL_MODE=transaction` is rejected by Django system checks.
- **Status:** Direct and session pooling are supported and verified.
  Transaction pooling is deliberately fail-closed until the tenant context is
  redesigned and tested through a real pooler. See
  [PGBOUNCER_MULTI_SCHEMA.md](PGBOUNCER_MULTI_SCHEMA.md).

## 3. Audit log retention and cold storage

- **Purpose:** Comply with retention policy; avoid unbounded growth of `audit_log` (per tenant).
- **Status:** Implemented as signed deterministic gzip JSONL archives,
  archive verification, exact-ID approval-gated purge, second-check legal
  holds, and operator-visible archive/hold records. See
  [AUDIT_RETENTION.md](AUDIT_RETENTION.md).
- **Partitioning decision:** Not performed automatically. Converting an existing
  PostgreSQL table requires a deployment-specific table swap and lock window;
  application startup DDL would be less reliable than bounded signed archives.

**Retention policy template (per tenant):**

- **Hot retention:** Keep last N days (e.g. 90) in `audit_log` for query and compliance.
- **Archive:** Export rows older than N days to cold storage (S3 bucket or equivalent); checksum/verify after export.
- **Purge:** After successful archive, DELETE or TRUNCATE partition for that period. Run as scheduled task (e.g. weekly) with idempotency and per-schema error handling.
- **Legal hold:** Support excluding specific date ranges or correlation_ids from purge when required by legal.

## 4. Real-time alerts for global/super-admin changes

- **Purpose:** Notify security/ops when high-impact changes occur (e.g. SiteSettings change, superuser creation).
- **Implemented:** Set env var `GLOBAL_CHANGE_ALERT_WEBHOOK_URL`; on SiteSettings `post_save` a background thread POSTs JSON to that URL. See siteconfig.models `_emit_global_change_alert`.
- **Design:** (1) Django signals (e.g. `post_save` on SiteSettings, or on User when `is_superuser` set). (2) In the signal handler, enqueue a task or call a webhook (e.g. Slack, PagerDuty). (3) Include change summary and actor; do not log secrets. Document in REPORTS/AUDIT_LOG.md or this doc.
- **Status:** Implemented for high/critical audit events and tenant membership
  role escalation/revocation, in addition to global changes.

## 5. Module and workflow map (concise)

- **Purpose:** Single reference: URL → view → template; key Celery tasks and management commands per area.
- **Location:** [REPORTS/AUDIT_LOG.md](../REPORTS/AUDIT_LOG.md) section “Module/workflow map” or [docs/MODULE_WORKFLOW_MAP.md](MODULE_WORKFLOW_MAP.md) (created). Cross-check FEATURE_GATE_PATH_MAP and feature registry.

---

**Status:** Repository-actionable items are implemented. Transaction pooling,
live cold-storage durability, and any PostgreSQL table repartitioning remain
deployment evidence gates, not hidden application defaults.
