# Search architecture

Tenant-safe, control-plane, and artifact search as a governed platform layer. No ad-hoc search per app; one search system with permission boundaries.

## Requirements

- **Tenant-safe entity search:** Students, staff, classes, invoices, etc. Scoped by request.school / tenant; filtered by role and policy.
- **Control-plane search:** Tenants, schools, blueprints, policies, workflows, dashboards, migrations, incidents. Only on manager.runmycampus.com/super/.
- **Document/report search:** Indexed documents and reports; scope by tenant and export restrictions.
- **Audit/incident search:** Audit logs and incidents; control-plane and tenant (where permitted).
- **Migration issue search:** Migration runs, validation errors, data issues (control-plane).
- **Marketplace/provider/app search:** App catalog, providers, packs; control-plane and tenant catalog.
- **Permission boundaries:** All results filtered by runtime, role, entitlements, and compliance (export_restrictions).

## Implementation direction

- Single search service/API that accepts `surface` (tenant_plane | control_plane), `request` (for tenant_ctx, user, tenant_runtime), and `query`/filters.
- Indexing strategy: which entities are indexed, refresh interval, and invalidation on policy/tenant change.
- Use existing registries and runtime for scoping; avoid hardcoded tenant/country branches in search logic.

## References

- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) (Law 2: runtime source of truth; Law 9: security/export centralized)
- [RUNTIME_COMPILATION_ORDER.md](RUNTIME_COMPILATION_ORDER.md) (registry, policy, compliance)
- RunMyCampus platform: `request.tenant_runtime`, `apps.platform_runtime.contracts` (ComplianceContext for export_restrictions)
