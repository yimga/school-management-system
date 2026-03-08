# Page-by-page UI and shell refactor map

Inventory derived from the real template tree. Every page family is mapped, every shell assigned, legacy/stock-admin/duplicate marked, and redesign priority noted. Use this to execute the frontend overhaul (Execution Master §3.1).

## Shell assignment (template root → surface)

| Shell | Base template | data-surface | Scope |
|-------|----------------|--------------|--------|
| MarketingShell | schools/marketing_base.html | marketing | runmycampus.com |
| ControlPlaneShell | control_plane_skeleton.html → control_plane_base.html | control-plane | manager.runmycampus.com/super/ |
| AdminOpsShell | admin/base_site.html | admin | manager.runmycampus.com/admin |
| TenantShell | portal_base.html, backend_base.html | tenant | tenant domains |

## Control plane pages (super/) — all ControlPlaneShell

| View / template | Page family | Legacy/duplicate | Priority |
|-----------------|-------------|------------------|----------|
| super_dashboard | dashboard | — | P1 |
| super_command_center | queue/command | — | P1 |
| super_create_school_wizard | wizard | — | P1 |
| super_usage | list | — | P2 |
| super_migration_cloud | list + actions | — | P1 |
| super_tenant_health | list | — | P1 |
| super_tenant_360 | record detail (tenant) | — | P1 |
| super_policy_diff | inspector/diff | — | P2 |
| super_workflow_packs_catalog | list | — | P2 |
| super_dashboard_packs_catalog | list | — | P2 |
| super_blueprints_catalog | list | — | P2 |
| super_policies_catalog | list | — | P2 |
| super_registries_overview | list/settings | — | P2 |
| super_compliance_overview | list | — | P2 |
| super_analytics_overview | analytics/report | — | P2 |
| super_pulse | dashboard/health | — | P1 |
| super_control_health | health | — | P2 |
| super_billing_dashboard | dashboard | — | P1 |
| super_support_dashboard | queue | — | P2 |
| marketplace/* (governance, app_catalog, etc.) | list/detail | — | P1 |
| platform_incidents_console | list/incident | — | P1 |
| customer_success_dashboard | dashboard | — | P2 |

**Plan §6.2 coverage:** Overview (dashboard), tenant 360, policy diff, migration console, provider board (marketplace), app governance (marketplace), health/incident boards (tenant_health, pulse, incidents). Runtime inspector and workflow simulator can be added as dedicated super views or embedded in tenant_360 / policy_diff.

## Admin backoffice (admin/) — AdminOpsShell

| Area | Page family | Stock-admin / legacy | Priority |
|------|-------------|----------------------|----------|
| admin/index | dashboard | Refined (Unfold) | P2 |
| Model list/detail (all apps) | list / record detail | Use table-system, form-system | P2 |
| SiteSettings, RegionConfig, etc. | settings | Refined | P2 |

## Tenant plane — TenantShell (role-filtered nav)

| Template / area | Page family | Legacy/duplicate | Priority |
|-----------------|-------------|------------------|----------|
| portal_base (dashboard, feeds) | dashboard | — | P1 |
| backend_student_list, backend_teacher_list, backend_guardian_list, backend_applicant_list | list | — | P1 |
| backend_student_create | wizard | — | P1 |
| feature_control_panel, workflow_hub, dashboard_hub | settings/list | — | P2 |
| finance (invoice_detail, parent finance) | record detail / list | Missing value in UI → use "—" (no TBD in production) | P2 |
| reports/*, reportcard_builder | report | — | P2 |
| portal/* (parent, teacher, documents, etc.) | mixed | — | P2 |

## Marketing plane — MarketingShell

| Template | Page family | Legacy/duplicate | Priority |
|----------|-------------|------------------|----------|
| marketing_landing, marketing_page, marketing_topic_page | marketing | — | P1 |
| marketing_blog_detail, marketing_funnel_dashboard | marketing | — | P2 |
| developer_portal, developer_sdk | marketing/settings | — | P2 |

## Page family rules (reminder)

- **Dashboard:** title_block, widget grid, dashboard pack–driven.
- **List:** title_block, filter_row, content_card, table-family, empty_state, loading_state.
- **Record detail:** title_block, action bar, content_card, aside panels.
- **Wizard/stepper:** steps, validation, sidebar summary where needed.
- **Settings/config:** section grouping, clear hierarchy.
- **Queue/inbox:** list family + status chips and actions.
- **Report/analytics:** title_block, chart-rules, export controls.
- **Inspector/diff:** side-by-side or panel layout, runtime-aware.

## Duplicated layout audit

- **Duplicate layout:** Any template that reimplements header + sidebar + content without extending the shell base should be refactored to use the correct base (control_plane_base, portal_base, backend_base, marketing_base, admin/base_site) and page family partials (title_block, filter_row, content_card, empty_state, loading_state).
- **Legacy-looking:** Pages not using design-tokens.css, surface-themes.css, or table-system/form-system/card-grammar should be brought into the system (see VISUAL_DEBT_BACKLOG.md).

## References

- docs/architecture/SHELL_IMPLEMENTATION.md
- docs/architecture/page_families.md
- docs/VISUAL_DEBT_BACKLOG.md
- templates/partials/page_families/
