# North Star: The Shopify, Salesforce, Amazon, AWS of Education & School Management

RunMyCampus is positioned as **the platform** for education and school management—one place to run operations, govern multiple schools, and scale with the same clarity and power that Shopify, Salesforce, Amazon, and AWS bring to their domains.

**Score bar:** **9.5/10 is the minimum target.** Eligibility for 9.5/10 is defined by [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) §12; **do not claim 9.5/10 until all §12 gates are satisfied** (see [BACKLOG_AND_DEFERRED_CLOSURE.md](BACKLOG_AND_DEFERRED_CLOSURE.md)). All configuration, UX, and execution standards are aligned to meet or exceed this bar. Path-to-10 work is tracked in `docs/PATH_TO_10_SCORECARD.md` and `docs/PHASE_10_BACKLOG.md`. See `docs/MASTER_PLATFORM_CHECKLIST.md` for the live ledger and verification commands.

## Positioning

- **Shopify of education**: One platform to run your school(s); apps, themes, and workflows that extend the core.
- **Salesforce of schools**: CRM-style visibility (School 360, health, adoption), governance, and a single control plane for districts and networks.
- **Amazon/AWS of school management**: Scale (many schools), reliability, clear operational surfaces (Control Plane, School registry, health, usage), and ecosystem (marketplace, integrations).

## UI & Copy Standards (Applied)

To match this positioning, user-facing language across the product has been aligned as follows:

| Avoid (internal/jargon) | Use (user-facing) |
|-------------------------|--------------------|
| Tenant Mission Control  | **Control Plane**  |
| Tenant Health           | **School Health**  |
| Tenant 360              | **School 360**     |
| Tenant registry         | **School registry**|
| Tenant Studio           | **Setup Studio**   |
| Provision Tenant        | **Add school**     |
| View as tenant          | **Open as school** |
| Tenant marketplace      | **App catalog**    |
| Tenant install path     | **Install path**   |
| Per-tenant              | **Per-school**     |
| Tenants (in lists)      | **Schools**        |

**Headers, breadcrumbs, nav, and layout** use the right-hand column. Technical identifiers (e.g. URL names like `tenant_health`, `switch_to_tenant`) remain unchanged for stability.

## Design System Alignment

- **Page archetypes** (role-home, setup-studio, decision-console, workbench, catalog, record-detail) are used so every major page has a clear intent. See `docs/ui/PAGE_ARCHETYPES.md`.
- **Design tokens and components**: `design-system-unified.css`, `platform-high-end.css`, and app-specific CSS follow the same variables and patterns. See `docs/archive/root_history/DESIGN_SYSTEM_CLEANUP_REPORT.md` and `CSS_MODERNIZATION_SUMMARY.md`.
- **Control Plane** (manager host): Single shell with School registry, School Health, Setup Studio, Command Center, Billing, Marketplace, and Configuration Engine—no “tenant” in labels.

## Integration Checklist

- [x] Control Plane and super dashboard: “Control Plane”, “School registry”, “Schools needing attention”, “Setup Studio”, “Open as school”.
- [x] All super_* breadcrumbs: “Control Plane” instead of “Tenant Mission Control”.
- [x] Nav and search: “School Health”, “Setup Studio”, “Search schools, incidents…”.
- [x] Marketplace (school-facing): “App catalog”, “Install path”, “for this school”.
- [x] Login, global discovery, find school: “School login”, “Create school”, “School finder”, “school portal”.
- [x] Backend impersonation: “Viewing as school”.
- [x] Footer and CTAs: “Add school” instead of “Provision Tenant”.
- [x] Control plane nav (Python): “Schools” group, “School Health”, “Setup Studio”.

Theme & experience, feature control, report library, design studios, live previews, workflows, AI/API usage, and system configuration use the same design system and terminology; “tenant” does not appear in headers, layout, or primary CTAs.
