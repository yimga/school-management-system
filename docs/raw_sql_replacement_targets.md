# Raw SQL Replacement Targets

**Purpose:** §2.4 "Replace avoidable business-logic SQL with ORM/service-layer logic" in the [embedded remediation plan](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md).

**Status:** **DONE** — All wraps complete; allowlist shrunk to repos + cache_utils only.

---

## 1. Priority order (non-migration)

| File | Reason | Action |
|------|--------|--------|
| `apps/evals/performance_optimization.py` | ~~Business-logic hotspot~~ **DONE** | Removed `pg_indexes` raw SQL; `get_missing_indexes()` returns static `RECOMMENDED_INDEXES` only |
| `apps/schools/health_utils.py` | ~~Tenant health~~ **DONE** | Wrapped in `schools/repositories/health_repository.py`; health_utils delegates; tests in test_health_repository.py |
| `apps/siteconfig/cache_utils.py` | current_setting read | **Keep as-is:** RLS session var `app.current_school_id`; no ORM equivalent; single module, allowlisted |
| ~~`apps/portal/onboarding_verification.py`~~ | ~~Migration check~~ **DONE** | Raw SQL moved to `siteconfig/repositories/migrations_repository.py`; portal delegates; allowlist updated; tests in test_migrations_repository.py + test_onboarding_verification.py |
| Commands (attach_audit_triggers, recover_database, etc.) | Operational | Keep; document only |

---

## 2. Already justified (keep)

- `apps/schools/rls_context.py` — single module for RLS session variables (SET/RESET app.current_school_id, rls_bypass); middleware delegates to it; no ORM equivalent.
- ~~`apps/schools/middleware.py`~~ — **DONE:** raw SQL moved to `rls_context.set_rls_school_id` / `reset_rls_school_id`; allowlist entry removed.
- `apps/schools/onboarding_service.py` — schema drop; operational.

---

## 3. Wrap retained raw SQL

- Retained usages must live in a single module per concern (e.g. `schools/rls_context.py`, `schools/repositories/health_repository.py`) with tests for tenant scoping.

---

## 4. Completion gate

- [x] evals/performance_optimization.py — raw SQL removed; allowlist entry removed
- [x] health_utils — raw SQL moved to repositories/health_repository.py; tests in test_health_repository.py; allowlist updated
- [x] cache_utils — documented as keep (RLS session var only)
- [x] middleware.py — raw SQL moved to rls_context.set_rls_school_id / reset_rls_school_id; allowlist entry removed; contract test in apps/schools/tests/test_rls_context.py
- [x] portal/onboarding_verification — raw SQL moved to siteconfig/repositories/migrations_repository.py; portal expected_count 0; siteconfig repo allowlisted (1); tests in siteconfig/tests/test_migrations_repository.py
- [x] Allowlist shrunk: only paths with raw SQL remain (repos + cache_utils); all expected_count 0 / wrapped paths removed from allowlist. lint_raw_sql_usage passes.

---

*Source of truth: [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §2.4.*
