# Security and production maturity

Identity, permissions, impersonation, secret handling, export restrictions, app scopes, test matrices, and rollout discipline (Execution Master Phase 7, §9 Deliverable 8).

## Requirements

- **Identity:** Centralized auth; MFA where policy requires; no ad-hoc session handling.
- **Permissions:** Role and permission checks via one path (e.g. Django auth, RBAC); no bypass in views.
- **Support impersonation:** When enabled, audit trail and clear UI indicator; scope limited; reversible.
- **Secret handling:** Provider secrets (payment, messaging, etc.) in secure storage; never in code or logs; rotate via admin/control plane.
- **Export restrictions:** Enforce runtime.compliance.export_restrictions; audit export events; block PII export when policy forbids.
- **App scopes:** Marketplace apps granted only requested scopes; scope checks at API boundary; revocable.
- **Test matrices:** Multi-country, multi-blueprint, multi-policy, multi-pack tests (e.g. platform_runtime.tests.test_runtime_by_blueprint_family, test_runtime_contract); admissions and finance tests with policy overrides.
- **Performance tests:** Critical paths (login, dashboard load, report generation) have performance targets; run in CI or nightly.
- **Rollout discipline:** Feature flags, canary/rollback control; no big-bang deploy of tenant-varying behavior.
- **Customer success / implementation / onboarding:** Ops surfaces for support (e.g. super support dashboard, customer success dashboard); onboarding flows documented; no improvisation in production.

## Implementation direction

- Use existing middleware and auth; ensure all tenant-facing views resolve permissions and export scope from runtime or central helpers.
- Audit logging: log impersonation, export, and scope use; queryable from control plane.
- Tests: extend platform_runtime and module tests to cover multiple policy/blueprint combinations; add performance tests where budgets are defined (see PERFORMANCE_BUDGETS_ARCHITECTURE).
- Document runbooks for rollout and rollback; use feature flags from runtime.flags.

## References

- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) (Law 9)
- apps/platform_runtime/contracts.py (SecurityContext, ComplianceContext)
- [PERFORMANCE_BUDGETS_ARCHITECTURE.md](PERFORMANCE_BUDGETS_ARCHITECTURE.md)
- apps/observability, apps/customersuccess
