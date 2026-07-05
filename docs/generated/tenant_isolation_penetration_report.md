# Tenant isolation penetration report

**Generated:** 2026-07-05T10:43:42.280209+00:00
**Verdict:** PENETRATION SUITE PENDING — RUN TESTS

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
| is_staff_tenant_admin_operator_surface | `apps.schools.tests.test_super_segment_tenant_guard` |
| operator_to_tenant_confinement_live | `apps.accounts.tests.test_tenant_host_isolation_revival` |
| forwarded_host_operator_spoof | `apps.schools.tests.test_forwarded_host_hardening` |
| operator_route_enumeration_coverage | `scripts.verify_tenant_cannot_reach_operator_routes` |
| support_helper_data_layer_authz | `apps.api.tests.test_support_agent_console` |

**Test run:** not_run

