# Catalog-backed forms and dropdowns

Part 1 / Part 4 item 7. Prefer **catalog-backed dropdowns** over free-text for country, region, grading, and language so data stays consistent and reportable.

## Pattern

- **Source of truth:** Use existing models as catalogs: `RegionConfig` (country/region), `GradingScaleConfig` / `EducationSystemProfile` (grading), `SiteSettings.default_language` / locale list (language). Optional: `Province` for state/province under a region.
- **Forms:** Bind choice fields to querysets (e.g. `RegionConfig.objects.all()`) or to a curated list (e.g. `settings.LANGUAGES`). Add an optional **"Other (specify)"** when the catalog cannot cover all cases: store the chosen catalog value in the main field and the free-text override in a separate field (e.g. `country_other`) only when "Other" is selected.
- **Validation:** Reject invalid codes; allow "Other" only when explicitly supported and then require the specify field.

## Where to apply first

- **Country/region:** School and Site Settings already use `School.default_region` (FK to RegionConfig). Prefer RegionConfig dropdown everywhere; deprecate or auto-fill `SiteSettings.country`/`region` from School.default_region where applicable.
- **Grading:** Use GradingScaleConfig / EducationSystemProfile for grading scale choices in school and report config.
- **Language:** Use Django's `LANGUAGES` or a locale list from RegionConfig/default_language; optional "Other (specify)" for rare locales.

## Implementation note

- Introduce a reusable **CatalogChoiceField** (or use `ModelChoiceField` with `RegionConfig.objects.all()`) and an optional `allow_other` + `other_field` pattern in forms. Audit existing forms and replace free-text country/region/grading/language fields with catalog-backed choice fields where appropriate.
