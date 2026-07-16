# apps/registries

> The platform's reference-data catalog: countries, currencies, locales,
> timezones, grade scales, fee categories, document types, and terminology packs.

**Tenancy:** SHARED (public schema; global catalog rows have no `school` at all, and the three tenant-override tables carry an explicit `school` FK)
**Scale:** 16 models · 11 migrations · 5 test modules · ~4.7k LOC

## What this app owns

Registries is the answer to "what does this platform know about the world before
any school signs up". It holds the seeded, operator-curated catalogs that every
other app reads when it needs to render a country picker, resolve a currency
symbol, decide what a term is called, or pick a grading scale: `CountryRegistry`,
`CurrencyRegistry`, `LocaleRegistry`, `TimeZoneRegistry`, `SubdivisionRegistry`,
plus the education taxonomy and the display registries for documents, fees, and
grade scales.

The design decision that shapes the whole app is the **two-layer split between a
global catalog and per-tenant overrides**. The catalog rows are platform-owned
and identical for every tenant — a school never edits `CurrencyRegistry`. When a
school needs to deviate, it does so through a *separate* table with a `school` FK
(`TenantAttendanceCode`, `TenantFeeTypeEntry`, `TenantGradeScaleOverride`) and a
resolver merges the two layers at read time. That is why this app is SHARED while
still supporting per-school customization, and it is why you should never add a
`school` column to a catalog model to "let one tenant tweak it" — add or extend
an override table instead.

The second decision is that **seeding is code, not fixtures**. Every catalog has
an idempotent `ensure_*_seed()` in `services.py`, composed by
`ensure_registry_baseline()`, so a fresh database self-heals to full global
coverage without a fixture load step.

## Key models

The 16 models split cleanly into global catalog vs tenant override:

| Model | Table | Purpose |
| --- | --- | --- |
| `CountryRegistry` | `registries_countryregistry` | ISO 3166-1 alpha-2 PK; carries default language/currency/timezone, writing direction, and `cockpit_override_payload` for operator overlays |
| `CurrencyRegistry` | `registries_currencyregistry` | ~195-currency ISO 4217 catalog with symbol and decimal places; seeded from `currency_seed.py` |
| `SubdivisionRegistry` | `registries_subdivisionregistry` | ISO 3166-2 states/provinces/regions under a country |
| `LocaleRegistry` | `registries_localeregistry` | Locale for number/date formatting and RTL |
| `TimeZoneRegistry` | `registries_timezoneregistry` | Canonical timezone list for school/region selection |
| `EducationLevelRegistry` | `registries_educationlevelregistry` | Primary / Secondary / Tertiary with per-country labels (`Elementary` in US, `Primary` in GB) |
| `EducationSystemTypeRegistry` | `registries_educationsystemtyperegistry` | Curriculum / delivery / pedagogy types, bucketed by category |
| `InstitutionTypeRegistry` | `registries_institutiontyperegistry` | Institution types (general, trade, technical, STEM, religious, international) |
| `GradeScaleRegistry` | `registries_gradescaleregistry` | Grading families and scale templates (0-20, 0-100, 4.0 GPA, letter); `range_definition` JSON holds min/max, pass threshold, steps |
| `AcademicTerminologyRegistry` | `registries_academicterminologyregistry` | Terminology packs (Principal vs Proviseur, Grade vs Class) |
| `CalendarSystemRegistry` | `registries_calendarsystemregistry` | Academic calendar presets (term count, start month) |
| `FeeCategoryRegistry` | `registries_feecategoryregistry` | Finance billing categories (Tuition, Application Fee, Transport, Lab Fee) |
| `DocumentTypeRegistry` | `registries_documenttyperegistry` | Admission/compliance document categories (Birth Certificate, National ID, Passport) |
| `TenantAttendanceCode` | `registries_tenantattendancecode` | **Override.** Per-school attendance codes, unique on `(school, code)` |
| `TenantFeeTypeEntry` | `registries_tenantfeetypeentry` | **Override.** Per-school fee line types; optional FK to `FeeCategoryRegistry` |
| `TenantGradeScaleOverride` | `registries_tenantgradescaleoverride` | **Override.** Per-school grade scale, optionally keyed by `context_key` (e.g. primary vs secondary) |

## Surfaces

This app has **no `urls.py`** and **no Celery tasks** — it is a library plus a
catalog, read through `services.py` and the resolvers. Its surface is:

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `services` | Every `ensure_*_seed()` and every `get_*_for_country()` reader; the app's front door |
| Module | `grade_scale_resolver` | `resolve_grade_scale_for_tenant()` — pure, max two SELECTs, no writes |
| Module | `currency` | `get_currency_symbol()` — curated map → `CurrencyRegistry` → bare ISO code |
| Module | `country_currency_map` | Static CLDR-derived country → legal-tender currency map |
| Module | `currency_seed` | The ISO 4217 seed list |
| Module | `tenant_registry_models` | The two `school`-FK override models (attendance codes, fee types) |
| Command | `seed_platform_registries` | Runs `ensure_registry_baseline()` — all catalogs |
| Command | `seed_country_localization_registries` | Locale / calendar / terminology seeding |
| Command | `seed_iso3166_subdivisions` | Subdivision catalog |
| Command | `seed_terminology_registry` | Terminology packs |
| Command | `verify_registry_coverage` | Gate: fails when active countries < `--minimum-countries` (default 195) |

## Before you change this

- **`ensure_country_registry_seed()` short-circuits at 190 rows.** The very first
  thing it does is `if CountryRegistry.objects.count() >= 190: return existing`.
  This makes it cheap to call on a hot path, but it means **adding a new field to
  the country seed will not backfill an already-seeded database** — the function
  returns before it reaches the `update_or_create` loop. Ship a data migration for
  the backfill; do not assume re-running the seed heals it. The other
  `ensure_*_seed()` functions do not have this guard and *do* `update_or_create`
  every row on each call.
- **Tenant attendance codes REPLACE the defaults; they do not merge.** The
  `TenantAttendanceCode` docstring says "Merged with defaults in
  `get_effective_attendance_codes`", but the function it names does the opposite:
  if the school has any active rows, those rows are returned *instead of* the
  defaults, and the defaults only apply when the school has none. Trust the code.
  A school that adds one custom code loses P/A/T/L unless it re-declares them.
- **Do not put a `school` FK on a catalog model.** The catalog is platform-owned
  and shared by every tenant; per-school deviation belongs in an override table
  read through a resolver. `TenantGradeScaleOverride`'s docstring spells this out:
  `GradeScaleRegistry` is the read-only platform catalog, and the override exists
  precisely so a tenant can pin a scale *without touching the catalog*.
- **`get_currency_symbol()` must never raise.** It is called from context
  processors and templates, so its registry lookup swallows every exception and
  falls back to the bare ISO code. It sentinel-caches only a **non-empty** load,
  which is deliberate: caching an empty result at import time (before the DB is
  ready) would permanently poison symbol rendering for the whole process.
- **Grade-scale resolution has a fixed precedence** documented at the top of
  `grade_scale_resolver.py`: exact `(school, context_key)` override → tenant
  default override (`context_key=""`) → `RuntimeDefaults.default_grading_scale` →
  first `GradeScaleRegistry` row matching the school's country → `None`. Overrides
  are also date-windowed via `effective_from` / `effective_until`; a row outside
  its window is skipped, not returned. If you add a resolution source, add it to
  that list and the docstring together.
- `country_currency_map.COUNTRY_CURRENCY` is **generated** reference data (CLDR
  via babel, validated against pycountry) shipped static so there is no runtime
  babel dependency. Regenerate it rather than hand-editing rows. Antarctica (AQ)
  is intentionally absent — it has no official currency.
