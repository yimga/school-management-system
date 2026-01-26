# KB: Managing the Dashboard Widget Catalog & Layout Seeds

## Where to edit
- Open **Site Settings ? Dashboard Widgets** in the admin panel (you can also edit apps/siteconfig/models_dashboard.py). Each DashboardWidget row controls a single card on the backend, teacher, or parent dashboard.
- Key fields:
  - widget_id: unique string that matches the data-widget-id attribute placed on each card’s HTML wrapper.
  - allowed_roles: JSON list (PARENT, TEACHER, BACKEND, etc.) to gate visibility.
  - default_column, order, allowed_sizes/value: used by the drag/drop catalog to render that card and persist its position.
  - widget_template: optional partial path if the card uses a custom template.

## Layout persistence
1. The UI drives `/api/dashboard/layout/` to fetch the current assignment for the logged-in user.
2. When a card is dragged, the JS posts the updated coordinates; the backend saves the payload into `DashboardLayout` (per user/role) which stores `items`, sidebar shortcuts, and widget meta such as sizes/variants.
3. To add a new movable block: assign it a data-widget-id, ensure the template includes the same ID, and seed a `DashboardWidget` entry with the appropriate `allowed_roles` so admins can enable or disable it.
4. The catalog is seeded by migrations under apps/siteconfig/migrations/*_seed_dashboard_widgets.py; edit or add a similar migration if you add new widgets.
5. Run `python manage.py migrate_dashboard_layouts` before you delete the legacy `DashboardUserPreference.dashboard_layout` field so every user’s old configuration lands in `DashboardLayout`.

## Tips
- Use the configuration UI to reorder cards per role without touching `{% include %}` statements.
- When debugging visibility, verify the user’s roles (accounts.models.UserProfile.role) and confirm the widget’s allowed_roles contains them.

*This KB entry can be referenced from the admin Help drawer so operators know where to manage layouts.*
