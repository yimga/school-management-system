# Reporting / BI / export architecture

Operational reporting, official/branded artifacts, scheduled reporting, materialized heavy reporting, export controls, and BI connector strategy (Execution Master §3.5, §7.3).

## Requirements

- **Operational reporting system:** Standard reports (attendance, grades, finance, admissions) driven by runtime (policy, registry, locale). No hardcoded region/currency/date.
- **Official/branded artifact system:** Report cards, transcripts, certificates as official documents; branding from runtime.branding; lifecycle per DOCUMENT_LIFECYCLE_ARCHITECTURE.
- **Scheduled reporting strategy:** Cron/celery jobs per tenant; scope and recipients from policy/entitlements; no cross-tenant leakage.
- **Materialized heavy report strategy:** Cache or materialize expensive aggregates; invalidation on data change; per-tenant scope.
- **Export controls:** Enforce runtime.compliance.export_restrictions; audit export events; no PII export without policy and audit.
- **BI/export connector strategy:** Secure API or connector for BI tools; scope by tenant and role; rate limits and audit.
- **Ministry/group rollups:** Cross-campus or group analytics only where policy and entitlements allow; aggregate-only where required.

## Implementation direction

- All report context (currency, date format, terminology, branding) from `request.tenant_runtime` or `build_tenant_runtime_for_tenant(tenant)` in jobs.
- Use existing `apps.reports` and report templates; ensure they consume runtime for locale and branding.
- Export and BI access: central permission check and audit logging; respect compliance.export_restrictions and security context.
- Performance: define query/timeout budgets for heavy reports; materialize where needed; see PERFORMANCE_BUDGETS_ARCHITECTURE.md.

## References

- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) (Law 2, Law 9)
- [DOCUMENT_LIFECYCLE_ARCHITECTURE.md](DOCUMENT_LIFECYCLE_ARCHITECTURE.md)
- apps/platform_runtime/contracts.py (ComplianceContext)
- RunMyCampus: all report context from `request.tenant_runtime` or `build_tenant_runtime_for_tenant(tenant)` in jobs.
