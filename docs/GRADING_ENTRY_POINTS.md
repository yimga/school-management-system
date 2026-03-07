# Grading entry points (Phase C)

All grading and report logic that depends on scale, pass mark, or letter bands **must** use tenant-driven config so behaviour is consistent and region-aware.

## Required usage

- **Scale / schema:** Use `get_scale_for_school(school)` or `get_grading_schema_for_school(school)` from `apps.siteconfig.tenant_config` and `apps.evals.grading` when computing grades, averages, or report card values.
- **Locale / currency in reports:** Use `get_tenant_locale(request=None, school=school)` for date format and currency; use the context-aware `format_currency` filter (e.g. `{% load region_format %}` then `{{ value|format_currency }}` with tenant context).
- **Report template family:** Use `get_report_template_family_for_school(school)` from `apps.siteconfig.tenant_config` when choosing layout or template variant for report cards.

## Where to hook

- **Evals (grades):** Any view or service that computes term average, GPA, or letter grade should call `get_scale_for_school(school)` (or equivalent) and use the returned scale for bands and pass threshold.
- **Reports:** Report rendering (e.g. `apps.reports.services`) should use `_region_display_context(school)` which includes `report_template_family` and locale; use it for formatting and template selection.
- **Custom fields:** Student/Staff custom attributes are defined via `get_custom_field_definitions(school, entity)` with `entity` in `["students", "staff"]`; definitions come from `School.settings["custom_field_definitions"][entity]`.

## Do not

- Hardcode pass mark, letter bands, or scale (e.g. 0–100, A–F) in views or templates.
- Hardcode currency symbols or date formats; use tenant locale and filters.
