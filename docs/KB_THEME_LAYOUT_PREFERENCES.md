# KB: Theme Brightness & Layout Persistence (Portal Preferences)

## Theme brightness options
- Portal Preferences now exposes four brightness choices: **Light**, **Dark**, **Classic**, and **High Contrast**.
- The selected option writes back to the UserPreference.theme_brightness field and is reflected immediately because the base template reads equest.user.preference.theme_brightness in the context processor (pps/siteconfig/context_processors.py).
- The admin can seed/override the palette by editing SiteSettings records (look for ThemeBrightnessChoice under Site Settings → Theme Brightness) and adjusting the CSS variables defined in static/css/theme/.

## Layout persistence
- Each dashboard widget includes a data-widget-id tied to DashboardWidget.widget_id; dragging cards posts the layout state to /api/dashboard/layout/ which saves the coordinates on DashboardUserPreference.layout.
- Portal Preferences offers a **Reset layout** button that clears the saved JSON for the current user, restoring the default catalog arrangement.
- The Portal Preference dropdown also controls which dashboard view is loaded (e.g., standard, ocused, nalytics) by toggling the UserPreference.dashboard_view field.

## Visible results
- When a user switches themes, the CSS load order ensures hero text, CTA buttons, footer badges, and map/gauge widgets remain legible across all modes (including High Contrast).
- Accessibility audits can be kicked off via the admin’s **Theme Preview** to ensure the new palette meets WCAG 2.1 AA.

*Use this KB entry to help support agents explain how to change a user’s branding or recover their layout when they report mismatched dashboards.*

## Role-based session timeouts
The admin can control how long each role stays authenticated via the `ROLE_SESSION_TIMEOUTS` mapping in `config/settings.py`. Defaults are:
- Superadmins/Admins: 30 minutes (environment variables `SESSION_TIMEOUT_SUPERADMIN`/`SESSION_TIMEOUT_ADMIN`)
- Department leads, finance, and IT: 1 hour
- Teachers: 4 hours
- Parents and students: 6 hours

These values can be overridden via environment variables and work alongside `SESSION_SAVE_EVERY_REQUEST` so active users still stay signed in.
