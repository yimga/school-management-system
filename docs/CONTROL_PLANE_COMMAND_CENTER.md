# Control-plane command center (super)

**Purpose:** `/super/` is the platform operator command center: engine-driven behavior, governance actions, unified navigation. Distinct from Django admin (backoffice CRUD).

## Super vs admin

| Use case | Where | Notes |
|----------|--------|------|
| Platform operations (tenant health, billing, migration, support, marketplace) | `/super/` (manager host) | Control-plane; requires SUPERADMIN or is_superuser. |
| Backoffice CRUD (models, users, site config) | `/admin/` | Django admin; superuser. |
| Tenant-facing backend | Tenant host, `/authentication/login/` | School staff; no `/super/` on tenant URLconf. |

Control-plane URLs live only in `config.manager_urls`; tenant URLconf does not include `super`. See `docs/CONTROL_PLANE_BOUNDARY_RULES.md`, `docs/CONTROL_PLANE_TEMPLATES.md`.

## Super entry points (apps.schools.super_urls)

- **Dashboard:** `super:dashboard`, `super:command_center`, `super:create_school_wizard`
- **Tenant ops:** `super:tenant_health`, `super:tenant_360`, `super:usage`, `super:control_health`, `super:api_school_lifecycle`, `super:api_approve_school`
- **Migration:** `super:migration_cloud`, `super:migration_rollback`
- **Billing:** `super:billing_dashboard`
- **Marketplace:** `super:marketplace_governance`, `super:blueprint_marketplace`, `super:app_catalog`, `super:marketplace_installation_health`, etc.
- **Blueprints/policies:** `super:blueprints_catalog`, `super:policies_catalog`, `super:registries_overview`
- **Support:** `super:support_dashboard`, `super:support_queue_fragment`, `super:support_assign_ticket`
- **Customer success:** `super:customer_success_dashboard`, `super:cs_api_*`
- **Other:** `super:sync_repair`, `super:runtime_inspector`, `super:workflow_simulator`, `super:ai_model_hub`, `super:global_ai_version`

All wrapped with `require_super_access_with_host` (host + SUPERADMIN/superuser).

## Engine-led behavior

- Tenant health: aggregated from activity and APIs; super_views and API v1 super endpoints.
- Usage: per-tenant usage data for billing.
- Migration: MigrationProfile, MigrationRun; wizard and rollback in super.
- Support: ticket queue and assign actions.
- Governance: approve school, lifecycle (activate/deactivate), policy bundle activate.

## Unified navigation

- Manager host: sidebar and nav use `super:dashboard` as hub; links to command_center, billing, marketplace, tenant_health, etc. Templates: `control_plane_base.html`, `control_plane_skeleton.html`; breadcrumbs to "Tenant Mission Control" (dashboard).
- Admin index (superadmin branch): links to Control plane, Command center, Billing; `templates/admin/index_superadmin.html`.

## References

- `apps/schools/super_urls.py`, `apps/schools/super_views.py`, `apps/schools/control_plane.py`
- `config/manager_urls.py` (includes super at `super/`)
- `docs/CONTROL_PLANE_BOUNDARY_RULES.md`, `docs/SHELL_ARCHITECTURE_MATRIX.md`
