# Finance app migrations

## Duplicate migration numbers

The `apps/finance/migrations/` folder has two migrations with the same number:

- `0019_add_finance_request_audit.py` – empty (no operations), depends on `0019_finance_request_audit`
- `0019_finance_request_audit.py` – creates `FinanceRequestAudit` model

This came from parallel branches. The merge migration `0022_merge_*` / `0023_merge_*` should resolve the dependency graph.

## "Table already exists" when running tests

If you see an error like **"table finance_financerequestaudit already exists"** when running `python manage.py test` or `migrate`:

1. **Fresh SQLite test DB:** The test runner creates a new DB and runs all migrations. If another migration path already created the same table, the second creation can fail.
2. **Fix options:**
   - **Squash:** Squash finance migrations (e.g. 0019–0023) into a single migration after confirming all envs are migrated, then remove the duplicate 0019.
   - **Safe migration:** In the migration that creates the table, use `RunPython` with a check (e.g. `connection.introspection.table_exists`) and only create if the table does not exist; or use a database-agnostic "IF NOT EXISTS" pattern if your DB supports it.
   - **CI:** Run tests with `--keepdb` once migrations have been applied, or exclude the finance app from full test runs until migrations are squashed/fixed.

## Running migrations

```bash
python manage.py migrate finance
python manage.py showmigrations finance
```

If you need to re-run from a clean state (e.g. local SQLite only):

```bash
# Backup first
cp db.sqlite3 db.sqlite3.bak
rm db.sqlite3
python manage.py migrate
```
