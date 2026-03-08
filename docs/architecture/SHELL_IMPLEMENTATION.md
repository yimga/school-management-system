# Shell implementation – template and surface mapping

Single source of truth for which template root and `data-surface` each experience plane uses. No hardcoded nav in templates; sidebars are built from runtime/role (control plane: `control_plane_nav`, tenant: `portal_sidebar_items`).

## Shell → template → data-surface

| Shell | Template root | data-surface | Domain / path |
|-------|----------------|--------------|---------------|
| **MarketingShell** | `schools/marketing_base.html` (extends `base.html`) | `marketing` | runmycampus.com |
| **ControlPlaneShell** | `control_plane_skeleton.html` → `control_plane_base.html` | `control-plane` | manager.runmycampus.com/super/ |
| **AdminOpsShell** | `admin/base_site.html` (Unfold) | `admin` | manager.runmycampus.com/admin |
| **TenantShell** | `portal_base.html`, `backend_base.html` | `tenant` | school.runmycampus.com, tenant domains |

Role shells (Principal, Teacher, Parent, Finance, Admissions, etc.) are implemented as role-filtered nav and dashboard content within **TenantShell**, not separate template trees. See `apps/siteconfig/portal_sidebar_items.build_portal_sidebar_items` and sidebar taxonomy.

## Design tokens and surface themes

- Load order: `design-tokens.css` → `surface-themes.css` (and plane-specific CSS).
- `surface-themes.css` keys off `html[data-surface="..."]` and body classes (e.g. `body.cp-surface`, `body.marketing-surface`, `body.admin-ops-surface`, `body.tenant-surface`).
- Tenant plane also applies school branding overrides from runtime (e.g. `--school-primary`, `--school-accent`).

## Sidebar data source

- **Control plane:** `apps.schools.control_plane_nav.build_control_plane_nav(request)` → `CONTROL_PLANE_NAV` (context).
- **Tenant:** `apps.siteconfig.portal_sidebar_items.build_portal_sidebar_items(request, site)` → `PORTAL_SIDEBAR_ITEMS`. Visibility is runtime-aware (entitlements.modules, flags) and role-based.

## References

- [experience_shells.md](experience_shells.md) – shell taxonomy and responsibilities
- [sidebar_navigation_taxonomy.md](sidebar_navigation_taxonomy.md) – grouping model and nav rules
- [ARCHITECTURE_LAWS.md](ARCHITECTURE_LAWS.md) – Law 5 (separate surfaces), Law 7 (governed sidebars)
