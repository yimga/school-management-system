# Raw SQL usage audit

Raw SQL appears in migrations, RLS helpers, reporting, and some application code. For each usage, confirm: tenant scoping, auth assumptions, and whether it can be replaced with ORM or wrapped in a repository/service.

**Classification key:** Performance | Reporting | Migration/repair | Unsafe business logic | Replaceable with ORM | Keep but wrap

**High-priority (application code, not migrations):**

| File | Purpose | Tenant scoping? | Auth assumptions? | Replace with ORM? | Wrap in service? |
|------|---------|-----------------|--------------------|--------------------|------------------|
| apps/schools/health_utils.py | Health checks | Review | Review | Consider | Yes |
| apps/schools/rls_context.py | RLS context | Yes (tenant) | Yes | No | N/A |
| apps/schools/middleware.py | Middleware | Review | Review | Consider | Yes |
| apps/evals/performance_optimization.py | Perf | Review | Review | Consider | Yes |
| apps/observability/views.py | Observability | Review | Review | Consider | Yes |
| apps/observability/monitoring.py | Monitoring | Review | Review | Consider | Yes |
| apps/siteconfig/cache_utils.py | Cache | Review | Review | Consider | Yes |
| apps/siteconfig/models.py | Model raw SQL | Review | Review | Consider | Yes |
| apps/schools/onboarding_service.py | Onboarding | Review | Review | Consider | Yes |
| apps/tenancy/tasks.py | Tenancy tasks | Review | Review | Consider | Yes |

**Migrations and scripts:** Most cursor.execute in migrations are one-off DDL/data; document and leave unless security-sensitive. Scripts (scripts/*, management commands) should be reviewed for tenant/path safety.

**Actions:** For each application-file row, add tenant_scoping and auth checks if missing; replace with ORM where feasible; otherwise wrap in a documented service layer.

**Remediation done:** observability/views.py — health-check `SELECT 1` raw SQL documented in-code (no tenant scope; staff-only views). Remaining application-file rows tracked in UX_PLAN_FULL_COMPLETION_REGISTER.

## Required remediation (non-negotiable)

These must be completed; no deferral to backlog. Track in [UX_PLAN_FULL_COMPLETION_REGISTER.md](../plan/UX_PLAN_FULL_COMPLETION_REGISTER.md).

1. **health_utils.py** — Confirm tenant scoping and auth; wrap in a small service if kept; add tests.
2. **rls_context.py** — Already tenant-scoped; document and keep.
3. **middleware.py** — Review raw SQL for tenant/path safety; wrap in service if needed.
4. **performance_optimization.py (evals)** — Review; add tenant scope if missing; wrap in service.
5. **observability/views.py, monitoring.py** — Review; restrict to staff/admin; wrap in service.
6. **siteconfig/cache_utils.py, models.py** — Review; add tenant scope where applicable; wrap in service.
7. **onboarding_service.py** — Review; ensure tenant-scoped; wrap in service.
8. **tenancy/tasks.py** — Review for tenant/path safety; document and add timeouts if needed.
9. **All application-file usages** — Replace with ORM where feasible; otherwise add tenant_scoping and auth checks and wrap in a documented service layer. Re-audit after changes.
