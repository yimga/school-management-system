# Architecture Certification Scorecard

- Generated: `2026-05-19T06:55:58.498402+00:00`
- Regenerate: `python scripts/generate_certification_artifacts.py --write`

## Grades

| Pillar | Grade | Evidence |
| --- | --- | --- |
| multi_tenancy | A- | RLS FORCE migrations + tenant middleware |
| rls_tenant_isolation | A- | scan_tenant_queryset_safety baseline 0 |
| security | A- | exception register product_violations=0 |
| admin_config_model | A | batch 1194 admin/config certified |
| studio_os | B+ | UX waves + route reverse audit |
| blueprints_packs | A- | governed installation + workflow packs |
| runtime_governance | A- | configuration console + change requests |
| marketplace | B+ | developer platform + catalog |
| api_developer_platform | A- | API Center + OpenAPI + scoped tokens |
| migration_onboarding | A- | migration cloud v3.33 + onboarding tests |
| observability | B+ | friction/RUM/SLO registry + public status |
| compliance_audit | A- | AuditLog + DSAR runbook + MAA v2 |
| billing_payments | C+ | finance tests; PSP partial external |
| feedback_customer_voice | B+ | feedback loop + KB + status |
| ux_accessibility | B | apple-class mechanical markers |
| tests_verifiers | A- | certification tests + phase gates |
| deploy_live_readiness | C+ | local parity artifacts; Render SHA partial |
| enterprise_procurement | B+ | procurement_packet + trust anchors |
| support_customer_success | B | customersuccess + health dashboards |
| competitive_readiness | B | CATEGORY DEFINING — REPO SCOPE |

**Composite (repo):** B+
