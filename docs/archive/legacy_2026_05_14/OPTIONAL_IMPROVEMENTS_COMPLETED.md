# Optional Improvements Completed

This document records the optional/future-work items that were implemented.

## 1. Portal sidebar order (config-driven)

- **Already in place:** `SiteSettings.portal_sidebar_order` (JSON list of item IDs), `build_portal_sidebar_items()` in `apps/siteconfig/portal_sidebar_items.py`, and context processor exposure as `PORTAL_SIDEBAR_ITEMS`.
- **Template:** `templates/partials/portal_sidebar.html` uses `PORTAL_SIDEBAR_ITEMS` when present and falls back to static markup. Admins can set `portal_sidebar_order` in Site Settings to control nav order.

## 2. Single design token file

- **Added:** `static/css/design-tokens.css` with shared CSS variables for Portal, Admin, and Backend (`--school-primary`, `--school-accent`, `--admin-accent`, `--portal-bg`, `--portal-font`, spacing/radius tokens, etc.).
- **Included first** in:
  - `templates/portal_base.html` (before `design-system-unified.css`)
  - `templates/admin/base_site.html` (before `design-system-unified.css`)
- Templates continue to override these with SITE/theme values where needed.

## 3. Extra graceful fallbacks in templates

- **Portal sidebar:** `SITE.portal_features` is now guarded with `{% if SITE %}` and `{% with portal_cfg=SITE.portal_features|default:None %}` / `{% if portal_cfg %}` so missing or empty config does not error.
- **Page titles:** `SITE.site_name` in block titles now uses `|default:"Portal"` where it was missing in:
  - `accounts/profile.html`, `accounts/notifications.html`, `accounts/direct_compose.html`, `accounts/messages.html`
  - `siteconfig/user_preferences.html`, `siteconfig/report_library.html`
- Report and logo templates already used `{% if SITE.logo %}` where appropriate.

## 4. Widget `chart_type` (model + API)

- **Already in place:** `DashboardWidget.chart_type` (migration `0052_dashboardwidget_chart_type`), `DashboardWidgetSerializer` includes `chart_type`, and backend dashboard passes `widget_chart_types_json` to the template for dashboard-charts.js.

---

*Completed as part of the optional improvements pass.*
