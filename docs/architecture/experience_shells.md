# Experience shells – taxonomy and template mapping

RunMyCampus has multiple experience surfaces. Each is backed by a **shell**: a consistent layout, nav, and chrome for that plane. This doc names shells and maps them to existing templates.

## Shell taxonomy

| Shell | Purpose | Domain / path |
|-------|---------|----------------|
| **MarketingShell** | Category positioning, demand gen, product storytelling, conversion | runmycampus.com (public) |
| **ControlPlaneShell** | Platform governance, tenant lifecycle, marketplace, observability, billing | manager.runmycampus.com/super/ |
| **AdminOpsShell** | Internal data ops, object-level maintenance, config admin | manager.runmycampus.com/admin |
| **TenantShell** | School operations, role dashboards, daily workflows | school.runmycampus.com, tenant custom domains |
| **PrincipalShell** | Curated nav for principal/admin: KPI, queue, approvals, governance | Tenant plane, role=ADMIN/LEADERSHIP |
| **TeacherShell** | Task-first, class-first, quick actions, compact density | Tenant plane, role=TEACHER |
| **ParentShell** | Mobile-first, progress feed, fees, messages | Tenant plane, role=PARENT |
| **StudentShell** | Progress, tasks, schedule, achievements | Tenant plane, role=STUDENT |
| **FinanceShell** | Ledger, invoices, reconciliation, reports | Tenant plane, finance role |
| **AdmissionsShell** | Pipeline, missing docs, reviews, decisions | Tenant plane, admissions |
| **ComplianceShell** | Audit, policies, reporting | Tenant plane / control plane |
| **MigrationOpsShell** | Migration console, data migration | Control plane |

Not all role shells have separate template trees today; many are implemented as role-filtered views and nav within TenantShell (portal_base).

## Template → shell mapping

| Template | Shell | Notes |
|----------|--------|------|
| base.html | MarketingShell (when serving public/marketing) | Also used for auth (login), errors, maintenance |
| schools/marketing_base.html | MarketingShell | Extends base; marketing navbar and chrome |
| control_plane_skeleton.html | ControlPlaneShell | Root for all /super/ pages; body.cp-surface; design tokens + surface-themes |
| control_plane_base.html | ControlPlaneShell | Extends skeleton; cp_content, data-driven sidebar (CONTROL_PLANE_NAV), collapse/compact, search |
| admin/base_site.html | AdminOpsShell | Unfold admin; Configuration Engine |
| portal_base.html | TenantShell | Tenant backend and portal; role-based dashboard entry |
| backend_base.html | TenantShell | Extends portal_base; backend console chrome |

## Shell responsibilities (target)

Each shell should define:

- Top navigation
- Sidebar / navigation behavior
- Page container widths
- Header pattern
- Action bar pattern
- Command / search surfaces
- Breadcrumbs
- Notifications placement
- Responsive behavior
- Density mode

Current templates already implement most of these; this taxonomy ensures new work assigns features to the correct shell and avoids mixing plane assumptions.

## Control plane shell (implemented)

ControlPlaneShell uses: **cp-surface** theme (surface-themes.css), **data-driven sidebar** from `apps.schools.control_plane_nav.build_control_plane_nav` (injected as CONTROL_PLANE_NAV), **collapsible section groups** and **compact icon-only mode** (toggle + localStorage), command/search in header, and page family patterns on signature screens (Tenant Health, Migration Cloud, Usage, Analytics). See sidebar_navigation_taxonomy.md for adding nav items.
