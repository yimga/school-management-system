# Tenant lifecycle external benchmark (Phase 1)

Generated from SaaS lifecycle principles — not vendor copy. Web research deferred; patterns mapped to existing repo surfaces.

## Patterns adopted in RunMyCampus

| Pattern | AWS-like | Shopify-like | Salesforce-like | Repo surface |
|---------|----------|--------------|-----------------|--------------|
| Idempotent provision | Yes | — | — | `complete_provisioning_for_school`, slug checks |
| Progress visibility | Status API | Setup checklist | Onboarding timeline | `provisioning_progress.py`, `rmc_tenant_provision_progress` |
| Retry without duplicate | Step functions | — | — | WorkflowRun + sync fallback |
| Audit trail | CloudTrail | — | Activity timeline | `SchoolProvisioningEvent`, `SchoolLifecycleStage` |
| Rollback / failed state | Stack rollback | — | — | `finalize_run(failed)`, remediation payload |
| Guided setup | — | Theme wizard | Setup assistant | Setup Studio JSON wizards |
| Offboarding export | Account close | Store close | Data export | `tenant_offboarding.py`, compliance inventory |
| Legal hold | — | — | — | `tenant_offboarding_policy.py` |
| Neighbor isolation | Account boundary | — | Org boundary | Tenant scoping, `# tenant-isolation-allow` |

## Honest gaps vs benchmark

- 14-step operator progress model vs 5-step workflow registry (extend, don’t fork)
- Unified notification facade with delivery status enum (partial — scattered modules)
- Postgres schema purge proof (environment-blocked on SQLite)
- Live Render SLA timing (external)
