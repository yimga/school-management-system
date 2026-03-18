# Trigger-based audit trail (blueprint)

Part 4.6 / Part 3.4. Design for world-class audit: **PostgreSQL triggers → tenant audit_log; INSERT-only; optional cryptographic chaining.**

## Goals

- **Who/What/Where/When/Why** plus `correlation_id` for each change.
- **Immutable** audit_log: INSERT-only; no UPDATE/DELETE on audit rows. DB permissions can enforce this.
- **Per-tenant:** One `audit_log` table per tenant schema (or a shared audit schema with tenant_id; plan prefers per-tenant table in tenant schema).
- **Trigger-based:** On INSERT/UPDATE/DELETE of audited tables, a trigger writes a row to `audit_log` (table_name, pk, action, old_values, new_values, user/session, timestamp, correlation_id). Application-level audit (e.g. Compliance middleware) remains; triggers provide a DB-level guarantee.

## Design

1. **Table `audit_log` (per tenant schema)**  
   Columns: id, table_name, record_id (pk), action (INSERT|UPDATE|DELETE), old_values (JSONB), new_values (JSONB), changed_by (user id or session), changed_at (timestamptz), correlation_id (UUID), request_meta (JSONB, optional).  
   Permissions: INSERT only for app role; no UPDATE/DELETE.

2. **Triggers**  
   For each audited table (e.g. people_studentprofile, finance_ledgerentry), attach a trigger that on INSERT/UPDATE/DELETE calls a stored procedure which INSERTs one row into `audit_log`.  
   **PII masking:** Never log passwords, card last-4, or full PII in old_values/new_values; redact in the trigger or in application before writing.

3. **Optional: cryptographic chaining**  
   Each row stores a hash of (previous_row_hash + current_row_content); tampering breaks the chain. To implement: add a `previous_row_hash` column to `audit_log` and a trigger (or application logic) that, on INSERT, sets `current_row_hash = hash(previous_row_hash || row_content)` using the previous row’s hash. First row uses a known seed. Not implemented in migration 0037; add per roadmap if required.

4. **Retention and cold storage**  
   Document retention policy; optionally archive old audit_log rows to cold storage (e.g. S3) and truncate after N days.

5. **Real-time alerts**  
   For global/super-admin changes (e.g. SiteSettings, superuser account), emit a webhook or alert to the security team.

## Trigger SQL (PostgreSQL)

Example trigger function and trigger for one audited table. Run per tenant schema (e.g. via RunPython that executes in tenant_context, or a RunSQL migration in people app applied per schema).

**Canonical implementation:** `apps/people/repositories/audit_repository.py` → `create_audit_trigger_function()`.  
Do not copy stale SQL here; see [people/AUDIT_LOG_TRIGGER_CONTRACT.md](people/AUDIT_LOG_TRIGGER_CONTRACT.md) for required columns (`correlation_id`, `request_meta`, `changed_by_id`, non-null JSON defaults).

```sql
-- Illustrative only — use Python helper above on deploy/seed.
-- INSERT must include correlation_id, request_meta, changed_by_id; old_values '{}' on INSERT; new_values '{}' on DELETE.
```

-- Example: attach to people_studentprofile (run per tenant schema).
-- CREATE TRIGGER audit_studentprofile
--   AFTER INSERT OR UPDATE OR DELETE ON people_studentprofile
--   FOR EACH ROW EXECUTE FUNCTION audit_trigger_fn();
```

**PII masking (plan 4.6):** Migration 0037 and command `attach_audit_triggers` strip these keys from `old_values`/`new_values`: `password`, `password_hash`, `secret`, `token`, `api_key`, `card_last4`, `card_number`, `ssn`, `social_security`. Add more in the migration's `REDACT_KEYS` or in the command. Never log full PII; extend redaction per table if needed.

**Applying to all tenant schemas:** Migration `0037_audit_triggers_tenant_schema` runs when you apply people migrations per tenant (`migrate_schemas --tenant`). To attach the same trigger to **additional tables** (e.g. finance_invoice, finance_payment):  
`python manage.py attach_audit_triggers --tables finance_invoice finance_payment`  
See [MIGRATION_RUNNER_TENANT_SCHEMAS.md](MIGRATION_RUNNER_TENANT_SCHEMAS.md).

## Status

- **Table:** `audit_log` (TenantAuditLog in [apps/people/models.py](../apps/people/models.py)) is created per tenant schema via people migrations. Migration: `0036_add_tenant_audit_log`.
- **Immutable audit_log (plan 4.6):** Run `python manage.py revoke_audit_log_permissions` to REVOKE UPDATE, DELETE ON audit_log in each tenant schema (from CURRENT_USER). Django models can still INSERT; application code must not update/delete audit rows. See [apps/people/management/commands/revoke_audit_log_permissions.py](../apps/people/management/commands/revoke_audit_log_permissions.py).
- **Triggers:** Attached by migration **0037_audit_triggers_tenant_schema** to `people_studentprofile` and `people_teacherprofile` per tenant. PII redaction applied in trigger. For other tables use: `attach_audit_triggers --tables <table1> <table2>`.
- **Application-level audit:** AuditLoggingMiddleware, SchoolProvisioningEvent remain in place.
