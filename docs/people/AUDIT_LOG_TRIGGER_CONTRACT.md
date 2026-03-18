# `audit_log` trigger contract (tenant schemas)

PostgreSQL function **`audit_trigger_fn()`** (defined in `apps/people/repositories/audit_repository.py`) runs on **INSERT/UPDATE/DELETE** of audited tables (e.g. `people_teacherprofile`). Each firing **INSERTs one row** into **`audit_log`** (`TenantAuditLog`).

## Why this doc exists

Django’s `TenantAuditLog` uses **NOT NULL** columns **without** PostgreSQL `DEFAULT` for several fields. The trigger must set **every non-auto column** explicitly. Omitting a column (or using the wrong name, e.g. `changed_by` instead of **`changed_by_id`**) causes **IntegrityError** during seeding and normal writes.

## Columns the trigger must set (keep in sync with the model)

| Column            | Trigger value |
|-------------------|---------------|
| `table_name`      | `TG_TABLE_NAME` |
| `record_id`       | row primary key as text |
| `action`          | `INSERT` / `UPDATE` / `DELETE` (`TG_OP`) |
| `old_values`      | JSONB; `{}` on INSERT; row snapshot on UPDATE/DELETE (minus redact keys) |
| `new_values`      | JSONB; row snapshot on INSERT/UPDATE; `{}` on DELETE |
| `changed_at`      | `now()` |
| `correlation_id`  | `''` (trigger has no request context) |
| `request_meta`    | `'{}'::jsonb` |
| `changed_by_id`   | `NULL` (trigger has no user context) |

`id` is serial — omitted.

## When you change `TenantAuditLog`

1. Update **`create_audit_trigger_function()`** in `audit_repository.py`.
2. Add a tenant migration that calls `create_audit_trigger_function` **or** rely on **`seed_render_users`** (refreshes the function per tenant on each predeploy).
3. Update this table.

## Related

- [AUDIT_TRAIL_TRIGGER_BASED.md](../AUDIT_TRAIL_TRIGGER_BASED.md) (design)
- `python manage.py attach_audit_triggers` — reapplies the same function before attaching triggers to new tables.
