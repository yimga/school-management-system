# Render / Tenant Migrations — Idempotent Pattern

When `migrate_schemas --tenant` runs on Render, the same migration can run in multiple tenant schemas. If a column (or table) was already added—e.g. by a previous partial deploy, manual fix, or re-run—Django’s normal `AddField` / `CreateModel` will raise **"column X of relation Y already exists"** and the pre-deploy fails.

To avoid that, **any migration that adds columns or tables that exist in tenant schemas** should be **idempotent**: safe to run more than once.

## Pattern: PostgreSQL

For **PostgreSQL** (Render), use raw SQL inside a `DO $$ ... EXCEPTION WHEN duplicate_column THEN NULL; END $$;` block so adding an existing column is a no-op:

```python
def add_columns_if_missing(apps, schema_editor):
    from django.db import connection
    with connection.cursor() as cursor:
        if connection.vendor == "postgresql":
            cursor.execute("""
                DO $$
                BEGIN
                    ALTER TABLE appname_modelname ADD COLUMN column_name type NOT NULL DEFAULT '';
                EXCEPTION WHEN duplicate_column THEN NULL;
                END $$;
            """)
        else:
            # SQLite: check PRAGMA table_info and only ADD if column not in list
            ...
```

Use **`SeparateDatabaseAndState`**: keep the usual `state_operations` (AddField etc.) so Django’s migration state stays correct, and use `database_operations=[RunPython(add_columns_if_missing, noop_reverse)]` for the actual DB changes.

## Migrations already made idempotent

| App          | Migration | What was fixed |
|--------------|-----------|----------------|
| schools      | 0015      | `wallpaper_url` on `schools_school` |
| schools      | 0016      | `compliance_region` on `schools_school` |
| schools      | 0017      | `hierarchy_path` on `schools_school` |
| schools      | 0018      | `trial_end_date` on `schools_school` |
| schools      | 0020      | `theme_pack_id` on `schools_school` |
| schools      | 0023      | (already idempotent) `branding_metadata`, `dedicated_db_alias`, `regional_cluster` |
| schools      | 0024      | (already idempotent) impersonation consent fields |
| schools      | 0025      | (already idempotent) `school_type` |
| schools      | 0027      | `country_code`, `subdivision_id` on `schools_school` |
| schools      | 0028      | `default_dashboard_slug`, `default_workflow_slug` on `schools_school` |
| automation   | 0002      | `schema_name`, `school_id` on automation approval/execution tables |
| automation   | 0004      | `rollback_snapshot`, `rolled_back_by_run_id` on `automation_migrationrun` |
| automation   | 0005      | `legacy_snapshot` on `automation_migrationrun` |
| portal       | 0021      | `country_code`, `education_type`, `plan_tier` on `portal_kbarticle` |
| portal       | 0023      | `school_id` on `portal_portalfeatureitem` |
| requests     | 0002      | `schema_name`, `school_id` on `requests_accessrequest` |
| communication| 0009      | `school_id` on all 11 communication tables (alertrule, announcement, etc.) |

## When to use this pattern

- Any **AddField** (or **CreateModel**) that runs in tenant context and touches tables that might already have been altered (e.g. `schools_school`, automation tables, or any table present in tenant schemas).
- Prefer this for **shared-app** migrations that are run per-tenant (e.g. when your setup runs all app migrations in each tenant schema).

## If another migration fails

If Render fails with **"column X of relation Y already exists"** (or **"relation X already exists"** for CreateModel):

1. Find the migration file and the exact `AddField` / `CreateModel` from the traceback.
2. Convert to **SeparateDatabaseAndState** + **RunPython**:
   - **PostgreSQL:** wrap each `ALTER TABLE ... ADD COLUMN` in `DO $$ BEGIN ... EXCEPTION WHEN duplicate_column THEN NULL; END $$;` (use `WHEN duplicate_table` for CREATE TABLE IF NOT EXISTS).
   - **SQLite:** use `PRAGMA table_info(table)` and only run `ADD COLUMN` if the column is missing.
3. Add the migration to the table above and push.

## References

- [MIGRATION_RUNNER_TENANT_SCHEMAS.md](../MIGRATION_RUNNER_TENANT_SCHEMAS.md) — how `migrate_schemas --tenant` works.
