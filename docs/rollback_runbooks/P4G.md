# Rollback runbook: Phase 4G exit

## Trigger conditions

- Group BOLA test fails on org-scoped queries.
- EMIS aggregate export fails for any active ministry pipeline.
- Group billing produces a consolidated AR figure that diverges from the sum of per-tenant ledgers.
- Granular ops verifier reports SMS gateway failover exceeding the SLO budget.
- Staff compliance clearance expiry fails to block attendance writes.

## Safe revert

1. Disable the sub-phase feature flag (`GROUP_CONSOLE_ENABLED`, `GROUP_BILLING_CONSOLIDATED`, `EMIS_AGGREGATE_PIPELINE`, `STAFF_COMPLIANCE_REGISTRY_ENFORCED`).
2. `git revert` the offending sub-phase merge.
3. Reset register status for sub-phase IDs to `IN_PROGRESS`.
4. Per-tenant fallback path remains operational; verify with smoke tests on a standalone tenant.

## Forbidden

- Bypassing BOLA tests by adding `# tenant-isolation-allow` markers without a documented reason that survives `scan_tenant_isolation_marker_quality.py`.
- Disabling EMIS export silently; ministries get an honest "export paused" status page.
