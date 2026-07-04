# Tenant Studio And Configuration Layout Rework Audit

Generated: 2026-07-04

## Scope

This pass implements the approved tenant Studio rework and applies the shared layout and preview contract to the preview-heavy tenant configuration surfaces that were identified in the audit.

Changed surfaces:

- Studio shell and all work modes that inherit it: Overview, Experience, Automation, Outputs, Launch, Control.
- Experience mode in-page canvas and iframe canvas.
- Studio Output embedded Report Card Builder.
- Studio Control embedded Feature Control.
- Standalone Feature Control.
- Standalone Report Card Builder.
- Dashboard Configuration Hub preview panel.
- Theme and Experience Hub tenant shell loading.
- Tenant header nav/search alignment.

## Layout Contract

- Studio mode pages now use a single owner layout via `studio-os--mode-owned`.
- The retired cockpit/right-rail layout is not loaded for mode-owned pages.
- The old giant blank viewport is removed from the active Studio mode path.
- Studio bottom/action bars are static page elements, not sticky overlays, so they no longer cover mode content.
- Experience mode renders live preview before deep settings, with the settings arranged inside the page flow.
- Workspace columns have bounded rail/context widths and a flexible main canvas so pages use available screen width without overlapping the sidebars.

## Live Preview Contract

New shared assets:

- `static/css/rmc-live-preview-contract.css`
- `static/js/rmc-live-preview-contract.js`

Every upgraded preview surface now exposes:

- Inline preview frame or preview target.
- Preview evidence row: source, scope, route, status.
- Retry inline action.
- Modal preview action.
- Popout preview action.
- Open in new tab action.
- Static fallback message when iframe rendering is blocked, slow, or unavailable.

The contract is attached to:

- `templates/studio_os/partials/experience_live_preview_pane.html`
- `templates/studio_os/partials/workspace/experience_iframe_canvas.html`
- `templates/siteconfig/partials/reportcard_builder_inner.html`
- `templates/siteconfig/feature_control_panel_content.html`
- `templates/siteconfig/partials/dashboard_configuration_hub_body.html`

## Header Contract

- Tenant header `More` is forced into the same inline nav row as Home, Finance, Messages, and Analytics.
- Tenant header search receives stricter width limits so the nav can move closer to center and avoid wrapping.

Primary file:

- `static/css/rmc-tenant-header-100x.css`

## Validation

Passed:

- `python manage.py check`
- `python manage.py makemigrations --check --dry-run`
- `python -m compileall -q apps config static\js`
- `python manage.py test apps.accounts.tests.test_role_permission_bridge --noinput`
- Static contract scan for all required markers.
- `python manage.py migrate --noinput` on the local SQLite environment, which applied the pending `people.0064_recordmergeoperation_and_merged_into` migration and closed the `people_studentprofile.merged_into_id` proof gap.
- Authenticated Studio Experience render smoke on `demo-school.runmycampus.com`:
  - status 200
  - `studio-os--mode-owned` present
  - `data-rmc-live-preview-contract` present
  - `data-rmc-preview-fallbacks` present
- Authenticated Feature Control render smoke on `manager.runmycampus.com`:
  - status 200
  - `Feature preview evidence` present
  - `Popout affected dashboard` present
- Authenticated tenant-host smoke on `smoke-tenant-admin.runmycampus.com` with a non-staff tenant ADMIN / school owner:
  - `/admin/`: status 200, `Tenant Administration`, `People Management`, and `Academic Structure` present; `Platform Backoffice` absent.
  - `/admin/login/?next=/admin/`: status 200 with tenant admin login; valid credentials redirect to `/admin/`.
  - `/configuration/`: status 200, `rmc-school-configuration-center` present; `rmc-platform-configuration-center` absent.
  - `/authentication/backend/`: status 200.
  - `/siteconfig/dashboard-configuration/`: status 200 with `Dashboard preview evidence`.
  - `/siteconfig/feature-control/?embed=1`: status 200 with `Feature preview evidence`.
  - `/siteconfig/reports/builder/`: status 200 with `Report preview evidence`.
- Manager-host smoke:
  - `/admin/` and `/admin/login/` on `manager.runmycampus.com` route to the existing operator policy and redirect to `/super/` when unauthenticated.
- Tenant/operator boundary regression proof:
  - `python manage.py test apps.schools.tests.test_tenant_middleware.TenantSuperPathRedirectBoundaryTests apps.studio_os.tests.test_studio_focus_layout.StudioFocusDedupeTests.test_tenant_studio_focus_sidebar_omits_operator_destinations apps.studio_os.tests.test_studio_os_operator_tenant_boundaries.TenantStudioLinkBoundaryTests --noinput`
  - Secure Django Client smoke on `tour-analytics.runmycampus.com`: `/super/command-center/` returns `302` to `/authentication/backend/`, never to `manager.runmycampus.com`.

Closed Proof Gaps:

- Dashboard Configuration Hub direct tenant proof now passes on a tenant host.
- Report Card Builder direct tenant proof now passes after applying the pending local migrations.
- Tenant `/configuration/` no longer routes to the platform configuration center.
- Tenant `/admin/` no longer redirects to `/authentication/backend/` and no longer renders manager/platform admin labels.
- Tenant `/super/command-center/` no longer bounces tenant subdomains/custom domains into the operator plane; resolved tenant hosts are kept tenant-local and redirected to the School Command Center.
- Tenant Studio rails and focus sidebar no longer emit operator-owned `super:*` / manager admin destinations.

Residual Local Test Environment Note:

- Targeted DB-backed Django test slices still time out in this local SQLite test environment. Direct Django Client smoke and command checks cover the changed tenant routes; a clean PostgreSQL-backed test profile should still be used for full CI-grade proof.

## Route Inventory

- Studio Experience: `/studio/experience/`
- Tenant Admin Console: `/admin/`
- Tenant Configuration Center: `/configuration/`
- Tenant Backend Console: `/authentication/backend/`
- Dashboard Configuration Hub: `/siteconfig/dashboard-configuration/`
- Feature Control: `/siteconfig/feature-control/`
- Report Card Builder: `/siteconfig/reports/builder/`

## Follow-Up Audit Trigger

When a clean PostgreSQL-backed test profile is available, rerun browser proof for:

- Tenant Admin Console login and index.
- Tenant Configuration Center.
- Dashboard Configuration Hub
- Report Card Builder
- Studio Output mode with embedded Report Card Builder
- Studio Control mode with embedded Feature Control
