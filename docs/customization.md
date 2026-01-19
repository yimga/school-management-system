# Customization & Site Settings

Phase 6 consolidates everything related to branding, portal toggles, report exports, and user-facing defaults so your next deployment stays on brand and aligned with school policy.

## Where to manage it
1. Visit `/siteconfig/customizer/` (staff only) to edit the single `SiteSettings` row via a friendly UI.
2. Use `/siteconfig/reports/` to download every registered list (students, teachers, subjects, fee collections, etc.).
3. Each user controls their own app behavior at `/siteconfig/preferences/` (timezone, dashboard view, refresh cadence, notification channels).

## Theme & branding
- Upload the current logo and optional background image, then pick a pre-built theme pack or override the colors directly (primary/accent + dark mode toggle).
- Each pack previews its palette, layout, and font family; selecting one automatically syncs colors and fonts on save.
- The portal base template consumes `SiteSettings.active_theme` (primary/accent, background, font) so every page follows the selected palette.

## Behavior & experience defaults
- `default_dashboard_view` and `default_refresh_rate` control what logged-in users see first and how often dashboards poll for updates.
- Maintenance mode blocks the public site while still allowing admins to reach the admin console.
- `notification_channels` determines which transports (email/SMS/app) the system uses for alerts and reminders.

## Portal & feature toggles
- Flip the parent/teacher portals or fine-grained portal modules (Messaging, Forums, Video, Documents) without touching templates.
- The portal sidebar, dashboards, and feature pages all consult `SITE.portal_features` to hide or show entries.
- Use `PortalFeatureItem` records (admin) to seed the per-feature content that parents see when a module is enabled.

## Reports & exports
- `report_downloads_enabled` gates access to the report library. When enabled, staff can download every major register as CSV/Excel/PDF.
- The `ReportTemplate` registry (models/siteconfig) wires named exports to handlers such as `students`, `teachers`, `subjects`, and `fee_payments`.
- Run `python manage.py migrate` after schema changes, then `python manage.py collectstatic --noinput` before redeploying so exports stay bundled with the latest code.

## Integrations & compliance
- Manage payment, notification, and analytics integrations from the admin `Integration` model so 3rd-party credentials stay in one place.
- Attach a `ComplianceProfile` (finance/payroll) to the site settings to keep payroll/run defaults aligned with the chosen jurisdiction.

## User-facing help
- The customizer makes every report downloadable and ensures theme switches are instant.
- Document these knobs in the welcome kit so admins know where to update logos, portal access, and report exports.
*** End Patch***
