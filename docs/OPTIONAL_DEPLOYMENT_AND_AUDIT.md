# Optional: Deployment and audit hardening

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
- **When:** Only if you want an extra safeguard; not required for correctness.

## 2. PgBouncer and connection pooling (multi-schema)

- **Purpose:** Scale connection count when many tenant schemas are in use; avoid exhausting PostgreSQL connections.
- **Considerations:** django-tenants switches `search_path` per request. With PgBouncer in transaction mode, the session is reset between transactions, so set `search_path` at the start of each request (middleware already does this). Use **session mode** if you need session-scoped search_path without re-set on every query.
- **Doc:** [PGBOUNCER_MULTI_SCHEMA.md](PGBOUNCER_MULTI_SCHEMA.md). Optionally add subsection to RUNMYCAMPUS_DEPLOYMENT.md when that file exists: recommended pool size, `ignore_startup_parameters` if needed, and that tenant resolution must set schema per request.

## 3. Audit log retention and cold storage

- **Purpose:** Comply with retention policy; avoid unbounded growth of `audit_log` (per tenant).
- **Design:** (1) Define retention (e.g. 90 days hot, then archive). (2) Celery task or management command: for each tenant schema, export rows older than N days to cold storage (e.g. S3, Parquet), then DELETE or TRUNCATE partition. (3) Document retention in [AUDIT_TRAIL_TRIGGER_BASED.md](AUDIT_TRAIL_TRIGGER_BASED.md) and in legal/compliance docs.
- **Optional:** Partition `audit_log` by month for efficient truncate/archive.

**Retention policy template (per tenant):**

- **Hot retention:** Keep last N days (e.g. 90) in `audit_log` for query and compliance.
- **Archive:** Export rows older than N days to cold storage (S3 bucket or equivalent); checksum/verify after export.
- **Purge:** After successful archive, DELETE or TRUNCATE partition for that period. Run as scheduled task (e.g. weekly) with idempotency and per-schema error handling.
- **Legal hold:** Support excluding specific date ranges or correlation_ids from purge when required by legal.

## 4. Real-time alerts for global/super-admin changes

- **Purpose:** Notify security/ops when high-impact changes occur (e.g. SiteSettings change, superuser creation).
- **Implemented:** Set env var `GLOBAL_CHANGE_ALERT_WEBHOOK_URL`; on SiteSettings `post_save` a background thread POSTs JSON to that URL. See siteconfig.models `_emit_global_change_alert`.
- **Design:** (1) Django signals (e.g. `post_save` on SiteSettings, or on User when `is_superuser` set). (2) In the signal handler, enqueue a task or call a webhook (e.g. Slack, PagerDuty). (3) Include change summary and actor; do not log secrets. Document in REPORTS/AUDIT_LOG.md or this doc.
- **Optional:** Extend to tenant-level “sensitive” actions (e.g. role escalation) if required.

## 5. Module and workflow map (concise)

- **Purpose:** Single reference: URL → view → template; key Celery tasks and management commands per area.
- **Location:** [REPORTS/AUDIT_LOG.md](../REPORTS/AUDIT_LOG.md) section “Module/workflow map” or [docs/MODULE_WORKFLOW_MAP.md](MODULE_WORKFLOW_MAP.md) (created). Cross-check FEATURE_GATE_PATH_MAP and feature registry.

---

**Status:** All items above are **optional**. Implement when compliance or operations require them.
