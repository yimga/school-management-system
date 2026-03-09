# Sidebar, Dashboard Widgets, and Provider Lists — Registry/Pack Target

**Purpose:** Document where sidebar, dashboard widgets, and provider lists live and their target layer (registry vs dashboard pack vs provider registry) so hardcoding is removed over time.

## Current state and target

### Portal sidebar

- **Current:** `apps.siteconfig.portal_sidebar_items.build_portal_sidebar_items(request, site)` builds items in code; order can be overridden by `SiteSettings.portal_sidebar_order` (JSON).
- **Target:** Sidebar items should be driven by a **sidebar registry** or **portal pack** (DB/registry) so new items and order are configurable without code. Until then, `portal_sidebar_order` remains the only runtime override; keep visibility logic in code but consider moving item definitions to a registry table.

### Dashboard widgets

- **Current:** `DashboardWidget` model (siteconfig) is the canonical catalog; seeds populate it. `default_dashboard_widgets(role)` and `get_dashboard_widget_choices(role)` in siteconfig/models.py still use fallback constants `DASHBOARD_WIDGET_OPTIONS` and `ROLE_WIDGET_DEFAULTS` when DB has no overrides. `get_tenant_dashboard_registry(school, role, page)` in dashboard_registry.py returns widgets from DashboardWidget + marketplace installed widgets.
- **Target:** **Dashboard pack / registry.** All widget choices and role defaults should come from `DashboardWidget` + tenant dashboard registry (and marketplace packs). Remove or minimize use of `DASHBOARD_WIDGET_OPTIONS` and `ROLE_WIDGET_DEFAULTS` once all environments have widgets seeded; new widgets must be added via DashboardWidget or packs, not code constants.

### Provider lists (integrations, payment, etc.)

- **Current:** Some provider lists (e.g. payment processors, notification channels) are hardcoded in code or in SiteSettings. Provider registry exists for extensibility.
- **Target:** **Provider registry.** List of available providers (payment, notification, etc.) should be registry-driven so new providers can be added without code. Use `apps.registries` or a dedicated provider registry table; tenant runtime resolves which provider is active per school.

## Enforcement

- **New sidebar items:** Prefer adding to a sidebar/portal registry or pack; avoid new hardcoded entries in portal_sidebar_items where possible.
- **New dashboard widgets:** Add via DashboardWidget (admin or migration), not by appending to DASHBOARD_WIDGET_OPTIONS.
- **New providers:** Register in provider registry (or registries app); do not hardcode in views or settings.

## Status

- **Done:** Documented target layers; DashboardWidget and get_tenant_dashboard_registry are the canonical widget source; dashboard_registry aggregates built-in + marketplace.
- **Next:** Migrate default_dashboard_widgets/get_dashboard_widget_choices to prefer DashboardWidget-derived lists when DB has widgets; then deprecate ROLE_WIDGET_DEFAULTS/DASHBOARD_WIDGET_OPTIONS as primary source.
