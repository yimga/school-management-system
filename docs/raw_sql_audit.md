# Raw SQL Usage Audit

**Purpose:** Inventory every `cursor.execute()` usage, excluding migrations, for Section 2.4 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Record purpose, tenant scoping, auth assumptions, and keep or replace decisions.

**Status:** **DONE** - All business-logic wraps are complete. The live allowlist is down to **six** retained repository modules (JSON `files` keys in `raw_sql_allowlist.json`), and CI enforces non-growth.

---

## 1. Non-migration files (allowlisted)

Source: `scripts/allowlists/raw_sql_allowlist.json`. Lint: `scripts/lint_raw_sql_usage.py`. The allowlist now contains only retained raw SQL with no ORM or framework equivalent.

| File | Expected count | Purpose | Tenant scoping | Decision |
|------|----------------|---------|----------------|----------|
| apps/people/repositories/audit_repository.py | 5 | Audit DDL (`search_path`, trigger function, drop/create trigger, revoke); each `execute` guarded for `OperationalError` / `ProgrammingError` / `DatabaseError` (debug log + re-raise) | Per-tenant schema | keep; staff-only repo; tested |
| apps/schools/repositories/health_repository.py | 3 | Tenant health PG catalog checks plus `count_table_rows()` for `tenant_health_check` | Tenant | keep; staff-only; tested |
| apps/schools/repositories/rls_repository.py | 1 | RLS verification against `pg_class` and `pg_namespace` | Tenant | keep |
| apps/schools/repositories/rls_context_repository.py | 4 | SET/RESET `app.current_school_id` and `app.rls_bypass` | Yes | keep; repository boundary; `rls_context` delegates |
| apps/siteconfig/repositories/rls_session_repository.py | 1 | `current_setting('app.current_school_id', true)` for tenant cache prefix | Read-only session GUC | keep; repository boundary; no ORM equivalent |
| apps/siteconfig/repositories/database_recovery_repository.py | 1 | SQLite `PRAGMA integrity_check` for `recover_database`; read-only `file:` URI + connect timeout; `sqlite3`/`OSError` on connect or `execute`/`cursor` → `None` | N/A | keep; staff-only; tested |

**Wrapped or delegated out of the allowlist:** `ensure_tenant_schemas`, `db_health_check`, `synthetic_probe`, `attach_audit_triggers`, `revoke_audit_log_permissions`, `portal/onboarding_verification`, `tenant_health_check`, `verify_tenant_rls`, `onboarding_service`, `apps/tenancy/tasks.py`, `apps/customers/repositories/schema_provisioning_repository.py`, and **`apps/siteconfig/cache_utils`** (RLS GUC read moved to **`rls_session_repository`**) now delegate to the retained files above or to framework primitives and no longer issue local raw SQL.

---

## 2. Migrations

All `cursor.execute()` usages in `*/migrations/*.py` remain allowed for schema, RLS, or PRAGMA work. They are excluded from the lint and not tracked here.

---

## 3. Per-usage record

Each non-migration file with raw SQL is listed in the allowlist with purpose, tenant scoping, and decision metadata. CI enforces parity through `scripts/lint_raw_sql_usage.py`.

## 4. Actions

- [x] Replace avoidable business-logic SQL in app code.
- [x] Wrap retained raw SQL in repository or helper boundaries with tests.
- [x] Shrink the allowlist as each replacement lands.
- [x] Keep critical paths on ORM, shared helpers, or framework primitives where possible.

---

## 5. Completion gate (Section 2.4)

- [x] Raw SQL is audited and governed by allowlist plus CI.
- [x] Critical paths use ORM, wrapped repositories, shared helpers, or framework primitives.
- [x] No ad-hoc tenant data access via raw SQL remains in application code.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) Section 2.4.*
