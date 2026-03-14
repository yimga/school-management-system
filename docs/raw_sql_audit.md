# Raw SQL Usage Audit

**Purpose:** Inventory every `cursor.execute()` usage (excluding migrations) for §2.4 of the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md). Record purpose, tenant scoping, auth assumptions, and keep/wrap/replace decision.

**Status:** **DONE** — All business-logic wraps complete; allowlist shrunk to repos + keep only; CI gate in place.

---

## 1. Non-migration files (allowlisted)

Source: `scripts/allowlists/raw_sql_allowlist.json`. Lint: `scripts/lint_raw_sql_usage.py`. **Allowlist contains only paths that have raw SQL** (repos + cache_utils); wrapped paths removed (expected_count 0 entries removed).

| File | Expected count | Purpose | Tenant scoping | Decision |
|------|----------------|---------|----------------|----------|
| apps/customers/repositories/schema_provisioning_repository.py | 2 | Schema provisioning (SELECT schemata, CREATE SCHEMA) | Tenant | keep; staff-only repo |
| apps/observability/db_liveness.py | 1 | Liveness SELECT 1; healthz/api_health use check_db_liveness() | None | keep |
| apps/people/repositories/audit_repository.py | 5 | Audit DDL (search_path, trigger function, drop/create trigger, revoke) | Per-tenant schema | keep; staff-only repo |
| apps/siteconfig/repositories/migrations_repository.py | 1 | Migration state SELECT (django_migrations); portal delegates | N/A | keep; staff/onboarding |
| apps/schools/repositories/health_repository.py | 5 | Tenant health (search_path, to_regclass, COUNT); tenant_health_check delegates | Tenant | keep; staff-only; tested |
| apps/schools/repositories/rls_repository.py | 1 | RLS verification (pg_class/pg_namespace); verify_tenant_rls delegates | Tenant | keep |
| apps/schools/repositories/tenant_schema_repository.py | 1 | DROP SCHEMA (onboarding kill-switch) | Tenant | keep |
| apps/schools/rls_context.py | 6 | SET/RESET app.current_school_id, app.rls_bypass | Yes | keep; session variable management |
| apps/siteconfig/cache_utils.py | 1 | current_setting('app.current_school_id', true) read-only | Read-only | keep; no ORM equivalent |
| apps/siteconfig/repositories/database_recovery_repository.py | 1 | SQLite PRAGMA integrity_check; recover_database delegates | N/A | keep; staff-only |

**Wrapped (no longer in allowlist):** ensure_tenant_schemas, db_health_check, synthetic_probe, attach_audit_triggers, revoke_audit_log_permissions, portal/onboarding_verification, tenant_health_check, verify_tenant_rls, onboarding_service, recover_database — all delegate to repos above or have 0 raw SQL.

---

## 2. Migrations

All `cursor.execute()` in `*/migrations/*.py` are allowed for schema/RLS/PRAGMA. Not listed here; excluded by lint.

---

## 3. Per-usage record (complete)

Each non-migration file with raw SQL is in the allowlist with purpose, tenant scoping, and decision. Raw SQL gate in CI: `scripts/pre_deploy_gate.sh` runs `lint_raw_sql_usage.py`.

## 4. Actions

- [x] Replace avoidable business-logic SQL (evals/performance_optimization.py → static RECOMMENDED_INDEXES).
- [x] Wrap retained raw SQL in repos (health_utils→health_repository; onboarding_verification→migrations_repository; etc.).
- [x] Allowlist shrunk: only repos + cache_utils; wrapped paths removed from allowlist.
- [x] Critical paths use ORM or wrapped repository; no ad-hoc tenant data access via raw SQL in app code.

---

## 5. Completion gate (§2.4)

- [x] Raw SQL is audited and governed (allowlist + CI).
- [x] Critical paths use ORM or wrapped repository; no ad-hoc tenant data access via raw SQL in apps.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.4.*
