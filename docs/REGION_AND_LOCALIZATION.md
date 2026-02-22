# Region and Localization (Developer Guide)

This guide describes how region and language are determined and how to use them in templates and code.

## Overview

- **Region** drives date format, currency symbol, number separators, timezone, and grading scale.
- **Language** is separate (Django i18n) but can be defaulted from the region and overridden by user preference.
- Context processors inject region and language data into every template. Template filters format values using that context.

## Context Processors

### `region_settings` (siteconfig)

Adds these keys to the template context:

| Key | Description |
|-----|-------------|
| `region` | `RegionConfig` instance for the active region |
| `region_code` | e.g. `"CMR"`, `"USA"` |
| `region_name` | Display name |
| `currency_symbol` | e.g. `"FCFA"`, `"$"` |
| `date_format` | Placeholder pattern: `DD/MM/YYYY`, `MM/DD/YYYY`, `YYYY-MM-DD` |
| `timezone` | e.g. `"Africa/Douala"` |
| `default_language` | Region default language code |
| `grading_scale` | Scale identifier for evals |
| `decimal_separator` | e.g. `"."`, `","` |
| `thousands_separator` | e.g. `","`, `" "` |
| `enable_multi_region` | From settings; toggles multi-region UI |

**Phase C – Report template family:** When building report context with a school, `_region_display_context(school)` also sets `report_template_family` from the school’s education system config (`EducationSystemProfile.config["report_template_family"]`). Use it to select layout (e.g. French Lycée vs UK standard). See `apps.siteconfig.tenant_config.get_report_template_family_for_school`.

**Custom field definitions:** School-level custom fields for students/staff are defined in `School.settings["custom_field_definitions"]` with keys `students` and `staff` (lists of `{key, label, type}`). Use `get_custom_field_definitions(school, "students")` or `("staff")` in admin or reports.

**Resolution order for region:**

1. Authenticated user’s **preferred_region** (from `UserPreference`)
2. Session `region_code`
3. Settings `REGION_CODE` (default region)
4. Fallback: default `RegionConfig` or a minimal in-memory object if DB fails

### `language_context` (siteconfig)

Adds:

| Key | Description |
|-----|-------------|
| `current_language` | Active language code |
| `current_language_name` | Display name (e.g. "Français") |
| `supported_languages` | List of (code, name) for switcher |

**Resolution order for language:**

1. `?language=` query parameter (if in supported list)
2. `django_language` cookie
3. Authenticated user’s **preferred_language** (from `UserPreference`)
4. Region’s `default_language`
5. Django’s default

## User Preferences

- **Model:** `UserPreference` (siteconfig) with `preferred_region` and `preferred_language`.
- **Access in code:** `request.user.preferences.preferred_region` / `preferred_language` (ensure `region_settings` / `language_context` use the same source for consistency).
- **Templates:** Use the context keys above; preferences are already applied by the context processors.

## Template Filters (region_format)

Load in templates: `{% load region_format %}`.

Filters **require** the `region_settings` context (they use `takes_context=True` and read from context). Normal views that use `RequestContext` get this automatically.

| Filter | Example | Notes |
|--------|---------|--------|
| `format_date` | `{{ invoice.due_date \| format_date }}` | Uses `date_format` (DD/MM/YYYY, etc.). |
| `format_currency` | `{{ amount \| format_currency }}` | Uses `currency_symbol`, `decimal_separator`, `thousands_separator`. |
| `format_number` | `{{ value \| format_number }}` or `{{ value \| format_number:0 }}` | Same separators; optional decimal places (default 2). |

**PDF / non-RequestContext:** If you render a template without `RequestContext` (e.g. some PDF or email flows), pass the same keys that `region_settings` provides (`date_format`, `currency_symbol`, `decimal_separator`, `thousands_separator`) in the context so these filters still work. See the docstring in `apps/siteconfig/templatetags/region_format.py`.

## Reports and Backend Code

- **Reports:** `apps/reports/services.py` uses `_region_display_context()` to pass region-based display settings into term/annual report context so report templates can show dates and currency in the active region’s format.
- **Grading:** `apps/evals/grading.py` maps region/grading scale and provides `CURRENCY_SYMBOLS` used by the context processor.

## Configuration and Docs

- **Default region / Buea:** `REGION_CODE`, `TIME_ZONE`, `ENABLE_MULTI_REGION` in `.env`; see `docs/CAMEROON_BUEA_SETUP_GUIDE.md` and `.env.example`.
- **Adding regions:** `RegionConfig` in admin; multi-school flow in `docs/MULTI_SCHOOL_ADD_NEW_SCHOOL.md`.
- **Checklist and roadmap:** `docs/REGION_AND_PLAN_IMPROVEMENTS_CHECKLIST.md`, `docs/PHASE7_NICE_TO_HAVE_ROADMAP.md`.
