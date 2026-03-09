# Control-Plane vs Tenant Templates

**Purpose:** Document which templates are control-plane only (manager host, /super/) vs tenant (school admin, portal) so the superadmin vs tenant boundary is explicit. All control-plane pages must extend control-plane bases only and must not render tenant-specific navigation or tenant-scoped data without explicit context.

## Control-plane template hierarchy

- **`control_plane_skeleton.html`** – Minimal shell (no tenant nav). Used only on manager host.
- **`control_plane_base.html`** – Extends skeleton; adds control-plane navbar, sidebar (`partials/control_plane_sidebar.html`), and `cp_content` block. **Use for all /super/ and manager-only HTML views.**
- **`partials/control_plane_sidebar.html`** – Control-plane navigation (Mission Control, Command Center, Billing, Marketplace, etc.). Not tenant sidebar.

## Control-plane-only templates (manager host / /super/)

These must **only** be rendered when the request is on the control-plane surface (manager host or path starting with `/super/`). They extend `control_plane_base.html` (or equivalent) and must not include tenant school context in the base layout.

| Template | View / usage |
|----------|----------------|
| `schools/super_dashboard.html` | super_dashboard_v2, super_command_center_v2 (dashboard) |
| `schools/super_usage.html` | super_usage |
| `schools/super_migration_cloud.html` | super_migration_cloud |
| `schools/super_pulse.html` | super_pulse |
| `schools/super_tenant_health.html` | super_tenant_health |
| `schools/super_tenant_360.html` | super_tenant_360 |
| `schools/super_control_health.html` | super_control_health_dashboard |
| `schools/super_workflow_packs.html` | super_workflow_packs_catalog |
| `schools/super_dashboard_packs.html` | super_dashboard_packs_catalog |
| `schools/super_blueprints_catalog.html` | super_blueprints_catalog |
| `schools/super_policies_catalog.html` | super_policies_catalog |
| `schools/super_registries.html` | super_registries_overview |
| `schools/super_command_center.html` | super_command_center_v2, mission queues |
| `schools/billing_dashboard.html` | billing_dashboard |
| `schools/super_create_school_wizard.html` | create_school_wizard |
| `schools/super_sync_repair.html` | sync_repair |
| `schools/super_policy_diff.html` | super_policy_diff |
| `schools/super_compliance_overview.html` | super_compliance_overview |
| `schools/super_analytics_overview.html` | super_analytics_overview |
| `schools/super_support_dashboard.html` | super_support_dashboard |
| `schools/super_support_queue_fragment.html` | support_queue_fragment |
| `schools/super_ai_model_hub.html` | ai_model_hub |
| `schools/super_global_ai_version.html` | global_ai_version |
| `schools/super_global_ai_version_progress.html` | global_ai_version_progress |
| `schools/super_runtime_inspector.html` | super_runtime_inspector |
| `schools/super_workflow_simulator.html` | super_workflow_simulator |
| `errors/500_control_plane.html` | 500 handler when on control-plane surface |
| Marketplace templates under `marketplace/` used from super (governance, sandbox, incidents, etc.) | marketplace_views (when served under /super/) |

## Tenant / shared templates (do not use for control-plane-only views)

- **`backend_base.html`** – Tenant admin shell (school context). Use for tenant staff dashboards and tenant-scoped admin.
- **`portal_base.html`** – Portal (parent/student/teacher). Tenant-scoped.
- **`base.html`** – Generic; avoid for control-plane to prevent mixing tenant and platform UI.

## Enforcement

- **Decorator:** All /super/ views are wrapped with `require_super_access_with_host` (host/surface + control-plane role). See `apps.schools.control_plane` and `apps.schools.super_urls`.
- **Role:** Control-plane access is `user_has_control_plane_access(user)` (SUPERADMIN or is_superuser). Tenant staff must not get manager-host capabilities.
- **URLconf:** Manager host uses `config.manager_urls`; `/super/` is included there only. Tenant host uses tenant URLconf and does not serve /super/.
