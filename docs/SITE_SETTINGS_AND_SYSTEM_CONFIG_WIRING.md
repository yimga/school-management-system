# Site Settings & System Config Wiring

This document describes how **SiteSettings** and related system config are wired so everything works end-to-end.

## 1. Context processors (templates get `SITE`, region, language)

- **`apps.siteconfig.context_processors.site_settings`**  
  Exposes `SITE` / `SITE_SETTINGS`, theme URLs, header toggles, report downloads, breadcrumbs, portal sidebar, pinned items, preview flags, finance request link.  
  Used by: all templates (via `config.settings` TEMPLATES).

- **`apps.siteconfig.context_processors.region_settings`**  
  Exposes `region`, `region_code`, `currency_symbol`, `date_format`, `timezone`, `grading_scale`, etc.  
  Uses: `RegionConfig.get_default()`, user `preferences.preferred_region`, session `region_code`, `settings.REGION_CODE`.

- **`apps.siteconfig.context_processors.language_context`**  
  Exposes language-related context. Uses user `preferences.preferred_language`, region default, cookie, GET param.

- **`apps.siteconfig.breadcrumb_context.breadcrumbs_context`**  
  Exposes `breadcrumbs` (path-based). Labels include `siteconfig` → "Site Settings", `feature-control` → "Feature Control".

- **`apps.siteconfig.breadcrumb_context.page_metadata_context`**  
  Exposes `page_title`, `page_description` for SEO.

## 2. Middleware

- **`MaintenanceModeMiddleware`**  
  If `SiteSettings.maintenance_mode` is True, returns 503 maintenance page for non-superusers; allows `/admin/` and `/authentication/`.  
  Uses cached `SiteSettings.get_solo()`.

- **`PreviewModeMiddleware`**  
  Handles preview mode and “act as role” for admins.

## 3. URLs (config/urls.py)

- `path('siteconfig/', include(('apps.siteconfig.urls', 'siteconfig'), namespace='siteconfig'))`
- Admin redirect: `path('admin/siteconfig/customizer/', ...)` → redirects to `/siteconfig/customizer/`

## 4. Siteconfig app URLs

- `/siteconfig/maintenance/` — maintenance view
- `/siteconfig/customizer/` — customizer (redirects to Site Settings message + theme packs)
- `/siteconfig/feature-control/` — Feature Control panel (toggles)
- `/siteconfig/feature-control/export/` — export features JSON
- `/siteconfig/feature-control/audit/` — audit log
- `/siteconfig/feature-control/api/` — GET features JSON
- `/siteconfig/preferences/` — user preferences
- `/siteconfig/theme-colors/`, `/siteconfig/reports/`, etc.

## 5. Feature Control panel

- **View:** `views_feature_control.feature_control_panel`
- **Permission:** `settings.feature_control`
- **State:** `SiteSettings.portal_features`, `SiteSettings.backend_feature_flags`, plus top-level booleans (`enable_parent_portal`, `enable_reports_pdf`, etc.).
- **Backend flags** (in `backend_feature_flags` JSON) include:
  - `block_report_download_if_outstanding_balance`
  - `block_report_download_if_outstanding_returns`
  - `carry_forward_arrears_on_rollover`
  - `block_promotion_if_outstanding_returns`
  - `require_guardian_finance_opt_in`, `allow_finance_access_requests`
  - `enable_entity_console`, `enable_entity_import`, `enable_api_schema_ui`, `allow_bulk_commit`
  - `notify_parent_on_absence`
- **Categories:** Academic, Administrative, Support, Finance & Permissions, Backend Tools, System & Notifications.
- **Apply:** `_apply_form_to_site()` writes to `SiteSettings` and saves; export/import use same keys.

## 6. Where SiteSettings is used in code

- **Reports:** `student_has_financial_clearance()`, `student_has_outstanding_returns()` use `backend_feature_flags`; report download views check these and `report_downloads_enabled` / `enable_reports_pdf`.
- **Finance:** `carry_forward_arrears()` used by rollover; invoice/reminder logic uses finance_* and notification flags.
- **Rollover:** `block_promotion_if_outstanding_returns`, `carry_forward_arrears_on_rollover` from `backend_feature_flags`.
- **Evals:** `grade_approval_enabled`, `reports_use_approved_grades_only`, etc.
- **Portal:** `enable_parent_portal`, `enable_teacher_portal`, `portal_features`, `portal_sidebar_order` (via `build_portal_sidebar_items`).
- **Theme:** `ThemePack`, `admin_theme_pack`, `primary_color`, `accent_color`, etc. resolved in context and admin/customizer.

## 7. User preferences (language/region)

- **Model:** `siteconfig.models.UserPreference` (related_name `preferences` on User).
- **Fields:** `preferred_language`, `preferred_region`, `timezone`, `dashboard_view`, etc.
- **Context:** `region_settings` and `language_context` use `request.user.preferences` when authenticated.
- **Dashboard:** `DashboardUserPreference` (related_name `dashboard_preferences`) holds theme, sidebar collapsed, pinned items.

## 8. Checklist (everything wired)

- [x] Context processors registered in `config.settings` TEMPLATES
- [x] MaintenanceModeMiddleware and PreviewModeMiddleware in MIDDLEWARE
- [x] siteconfig URLs included under `siteconfig/`
- [x] Feature Control panel shows and saves all backend flags (including report block and arrears carry-forward)
- [x] Breadcrumb labels for siteconfig, feature-control, customizer
- [x] Customizer view passes `site_settings_url` to admin Site Settings
- [x] Portal sidebar links to Feature Control, Customizer, Site Settings (admin)
