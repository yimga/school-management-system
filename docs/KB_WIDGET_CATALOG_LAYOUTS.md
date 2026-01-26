# KB: Managing the Dashboard Widget Catalog & Layout Seeds

## Where to edit
- Open **Site Settings → Dashboard Widgets** in the admin panel (you can also edit pps/siteconfig/models_dashboard.py). Each DashboardWidget row controls a single card on the backend, teacher, or parent dashboard.
- Key fields:
  - widget_id: unique string that matches the data-widget-id attribute placed on each card’s HTML wrapper.
  - llowed_roles: JSON list (PARENT, TEACHER, BACKEND, etc.) to gate visibility.
  - layout_column, layout_row, ariant, size: used by the drag/drop catalog to render that card and persist its position.
  - widget_template: optional partial path if the card uses a custom template.

## Layout persistence
1. The UI drives /api/dashboard/layout/ to fetch the current assignment for the logged-in user.
2. When a card is dragged, the JS posts the updated coordinates; the server stores them on DashboardUserPreference.layout tied to the user.
3. To add a new movable block: assign it a data-widget-id, ensure the template includes the same ID, and seed a DashboardWidget entry with is_configurable=True so admins can enable or disable it.
4. The catalog is seeded by migrations under pps/siteconfig/migrations/*_seed_dashboard_widgets.py; edit or add a similar migration if you add new widgets.

## Tips
- Use the configuration UI to reorder cards per role without touching {% include %} statements.
- When debugging visibility, verify the user’s roles (ccounts.models.UserProfile.role) and confirm the widget’s llowed_roles contains them.

*This KB entry can be referenced from the admin  Help drawer so operators know where to manage layouts.*
