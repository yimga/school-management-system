# Sidebar and navigation surgery

Actual menu inventory, surface-by-surface and role-by-role nav plan, and rules for remove/merge/favorites (Execution Master §3.2, §6.5).

## Control plane sidebar — current inventory

**Source:** `apps.schools.control_plane_nav.build_control_plane_nav(request)`. Rendered by `partials/control_plane_sidebar.html`.

| Group | Items | Notes |
|-------|--------|--------|
| (none) | Dashboard, Command Center, Provision tenant, Billing, Support | Overview + ops |
| Marketplace | Governance, Blueprints, App catalog, Customer Success | Governance |
| (none) | Migration, Usage, Pulse, Tenant Health, Compliance, Analytics, Incidents | Operations + insights |
| Packs & registries | Registries, Blueprints, Policies, Workflow Packs, Dashboard Packs | Governance |
| (none) | Configuration Engine | Link to admin |

**Behavior:** Grouped nav, collapse/expand sections, compact icon mode (localStorage), mobile offcanvas. Active state by `request.path == item.url`. No hardcoded nav in template; all from `CONTROL_PLANE_NAV`.

**Surgery:** No removals required; grouping matches plan. **Done:** "Runtime inspector" and "Workflow simulator" added as super URLs and nav items (super:runtime_inspector, super:workflow_simulator). **Done:** Favorites/pins in control plane sidebar (Phase 8): DashboardUserPreference.control_plane_pinned_items, PINNED_CONTROL_PLANE_ITEMS in context, Quick access section in control_plane_sidebar.html.

## Tenant (portal) sidebar — current inventory

**Source:** `apps.siteconfig.portal_sidebar_items.build_portal_sidebar_items(request, site)`. Rendered by `partials/portal_sidebar.html`. Visibility: runtime (entitlements.modules, flags) and role (Teacher, Parent, Staff, etc.).

**Sections (by role):** Home, Account, Communication, My Workflow, Learning Management / Children & Learning, Support, Content & Documents, People & Access, Academic Management, Financial Management, Analytics & Reports, Admin Panel. Role shells see a slice; staff see full set.

**Behavior:** Pinned items (Quick access), section titles, collapse toggle, resizable width, mobile drawer. Config-driven order via `site.portal_sidebar_order`; runtime filters by entitlements and flags.

**Surgery:**
- **Remove:** None mandated; any dead URL is already omitted by `_safe_reverse`.
- **Merge:** Avoid duplicate section labels (e.g. "Communication" appears once per role slice); already de-duplicated by section order.
- **Favorites/pins:** Implemented (PINNED_SIDEBAR_ITEMS, user preferences). Keep.
- **Secondary:** "Configuration Engine" and admin-only links are in Admin Panel section; no change.

## Admin backoffice sidebar

Unfold app list + custom links. Grouping follows Django app order and custom link injection. No separate surgery doc; keep Unfold grouping and add custom links per taxonomy (Content/config, Records/tools, Maintenance, Support, Data/admin) where needed.

## Role-by-role nav plan (tenant)

| Role | Primary sections | Hide |
|------|-------------------|------|
| Teacher | Home, Account, Communication, My Workflow, Learning Management, HR, Settings (Portal Stats) | Admin Panel, People, Finance, Analytics |
| Parent | Home, Account, Communication, My Workflow, Children & Learning, Performance Tracking, Portal Tools | Admin Panel, People, Academic/Financial Management |
| Staff/Admin | Full set including Support, Content & Documents, People & Access, Academic, Financial, Analytics, Admin Panel | — |
| Student | Home, Account, Communication, progress/tasks | Backend, Admin |

Governed by `build_portal_sidebar_items`; no hardcoded role branches in templates—only in the single builder.

## Surface-by-surface summary

| Surface | Nav source | Grouping | Favorites | Compact | Mobile |
|---------|------------|----------|-----------|---------|--------|
| Marketing | marketing_navbar_primary (context) | Top nav only | — | — | Hamburger |
| Control plane | control_plane_nav | Grouped, section labels | Optional future | Yes | Offcanvas |
| Admin | Unfold | App-based | — | — | Unfold responsive |
| Tenant | portal_sidebar_items | Section titles, role slice | Pins | Yes | Drawer |

## References

- apps/schools/control_plane_nav.py
- apps/siteconfig/portal_sidebar_items.py
- docs/architecture/sidebar_navigation_taxonomy.md
- docs/architecture/ARCHITECTURE_LAWS.md (Law 7)
