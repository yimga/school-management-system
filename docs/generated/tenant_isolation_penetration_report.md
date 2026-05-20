# Tenant isolation penetration report

**Generated:** 2026-05-20T02:18:30+00:00  
**Verdict:** PENETRATION SUITE READY — REPO SCOPE

| Scenario | Module |
|----------|--------|
| cross_tenant_pk_guess | `apps.security.tests.test_boundary_penetration` |
| forged_session_school_id | `apps.security.tests.test_boundary_penetration` |
| slug_host_manipulation | `apps.security.tests.test_boundary_penetration` |
| host_header_manager_export | `apps.security.tests.test_boundary_penetration` |
| rls_query_isolation | `apps.security.tests.test_boundary_penetration` |
| impersonation_without_reason | `apps.security.tests.test_boundary_penetration` |
| impersonation_audit_integrity | `apps.accounts.tests.test_impersonation_audit_integrity` |
| rls_force_migration_contract | `apps.tenancy.tests.test_rls_boundary_contracts` |
| platform_route_from_tenant | `apps.security.tests.test_tenant_route_leakage` |

**Test run:** pass (16 OK, 2 skipped on SQLite for Postgres GUC validation)
