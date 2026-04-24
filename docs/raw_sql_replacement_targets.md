# Raw SQL Replacement Targets

**Purpose:** §2.4 "Replace avoidable business-logic SQL with ORM/service-layer logic" in the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

**Status:** **DONE** — All wraps complete; allowlist is **six** retained repository modules (see [raw_sql_audit.md](raw_sql_audit.md) §1 and `scripts/allowlists/raw_sql_allowlist.json`). **`apps/siteconfig/cache_utils`** and **`apps/schools/rls_context`** delegate to repositories and **do not** appear on the allowlist.

---

## 1. Priority order (non-migration)

| File | Reason | Action |
|------|--------|--------|
| `apps/evals/performance_optimization.py` | ~~Business-logic hotspot~~ **DONE** | Removed `pg_indexes` raw SQL; `get_missing_indexes()` returns static `RECOMMENDED_INDEXES` only |
| `apps/schools/health_utils.py` | ~~Tenant health~~ **DONE** | Wrapped in `schools/repositories/health_repository.py`; health_utils delegates; tests in test_health_repository.py |
| `apps/siteconfig/cache_utils.py` | ~~RLS GUC read~~ **DONE** | Delegates to **`repositories/rls_session_repository.py`** (`current_setting('app.current_school_id', true)`); allowlist holds the repo only |
| ~~`apps/portal/onboarding_verification.py`~~ | ~~Migration check~~ **DONE** | Raw SQL moved to `siteconfig/repositories/migrations_repository.py`; portal delegates |
| Commands (attach_audit_triggers, recover_database, etc.) | Operational | Keep; document only |

---

## 2. Already justified (keep)

- `apps/schools/rls_context.py` — public API + normalization for RLS session variables; SQL only in **`repositories/rls_context_repository.py`**; middleware delegates; no ORM equivalent; **not** allowlisted.
- ~~`apps/schools/middleware.py`~~ — **DONE:** delegates to `rls_context` / repository stack; allowlist entry removed.
- `apps/schools/onboarding_service.py` — schema drop; operational.

---

## 3. Wrap retained raw SQL

- Retained usages live in repository modules per concern (`rls_context_repository`, `rls_session_repository`, `health_repository`, `audit_repository`, `rls_repository`, `database_recovery_repository`) with tests for tenant scoping and fail-closed behavior where applicable.

---

## 4. Completion gate

- [x] evals/performance_optimization.py — raw SQL removed; allowlist entry removed
- [x] health_utils — raw SQL moved to repositories/health_repository.py
- [x] cache_utils — delegates to **rls_session_repository**; allowlist = repo file only
- [x] rls_context — delegates to **rls_context_repository**; allowlist = repo file only
- [x] middleware.py — delegates; no allowlist entry on middleware
- [x] portal/onboarding_verification — migrations_repository path; allowlist updated historically
- [x] Allowlist: only the six §2.4 repository paths retain `cursor.execute`; `lint_raw_sql_usage` passes

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.4.*
