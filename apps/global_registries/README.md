# apps/global_registries

> The bounded-context ownership surface for global reference data — countries,
> calendars, grade scales, regions — plus the canonical field-schema registry
> that interop transfers validate against.

**Tenancy:** SHARED (public schema; listed in `SHARED_APPS` at `settings.py:3889`)
**Scale:** 8 proxy models · 1 migration · 3 test modules · ~0.7k LOC

## What this app owns

This app owns an *import path*, not a set of tables. It is one of four
bounded-context ownership surfaces in the repo (with `runtime_blueprints`,
`plans_entitlements`, and `policies_rules`) created so domain code can migrate
off `apps.siteconfig.*` and `apps.registries.*` without moving a single table
first. Its `models.py` docstring states the intent plainly: these proxy-owner
models "provide a stable registry import layer while current data is still
stored across `apps.registries` and legacy siteconfig models."

The mechanism is a runtime factory, `_proxy_model(legacy_model, app_label=..., doc=...)`,
which builds each class with `type()` and a `Meta` carrying `proxy = True` plus
`app_label = "global_registries"`. Django registers them as this app's models;
the rows keep living in the originating app's table. `migrations/0001_proxy_owner_models.py`
is `CreateModel(fields=[], options={"proxy": True}, bases=("siteconfig.educationsystemprofile",))`
eight times over — it creates **no tables at all**, it only teaches the migration
graph that these proxies exist.

The one piece of genuine, non-proxy logic here is `schema_mapping.py`: a registry
mapping tenant-custom field names onto 13 canonical global field types
(`identity`, `demographic`, `contact`, `enrollment`, `guardian`, `academic`,
`attendance`, `finance_summary`, `medical`, `compliance`, `consent`,
`curriculum`, `dual_profile`). Its purpose, per its docstring, is so interop
transfer envelopes "fail loudly when a transferable record would lose
information at a boundary". Each `CanonicalField` carries `transferable` and
`pii` flags — e.g. `medical.allergies` is `pii=True, transferable=False`.

## Key models

**Every model here is a proxy built at import time by `_proxy_model()`.** There
is no hand-written model class in this app, no table of its own, and nothing to
migrate. The rows live in `apps.registries`, `apps.academics`, and
`apps.siteconfig` — the table names below are the *legacy owners'* tables, which
is exactly why the `siteconfig_` prefix survives.

| Kind | Proxy | Table (owned by) | Purpose |
| --- | --- | --- | --- |
| Platform catalog | `EducationSystemProfile` | `siteconfig_educationsystemprofile` | Education system profiles |
| Platform catalog | `Province` | `siteconfig_province` | Province / state registry entries |
| Platform catalog | `RegionConfig` | `siteconfig_regionconfig` | Region configuration |
| Platform catalog | `SystemFeature` | `siteconfig_systemfeature` | System feature registry data |
| Platform catalog | `TenantSystem` | `siteconfig_tenantsystem` | Tenant education-system attachments (has a `school` FK) |
| Global experience | `GradingScaleConfig` | `siteconfig_gradingscaleconfig` | Grading scale configurations |
| Global experience | `WeatherLocation` | `siteconfig_weatherlocation` | Weather / location registry entries |
| Academics | `HolidayCalendar` | `siteconfig_holidaycalendar` | Holiday calendars (imported from `apps.academics`) |

`models.py` additionally re-exports 13 concrete registries from
`apps.registries` unchanged (`CountryRegistry`, `CurrencyRegistry`,
`GradeScaleRegistry`, `LocaleRegistry`, `TimeZoneRegistry`, `SubdivisionRegistry`,
and friends) — those are plain re-exports, not proxies, and they remain
`apps.registries` models.

## Surfaces

| Kind | Name | Notes |
| --- | --- | --- |
| Module | `schema_mapping` | Public API per its `__all__`: `CANONICAL_FIELD_TYPES`, `CanonicalField`, `MappingValidation`, `SchemaMappingError`, `canonical_fields()`, `lookup()`, `map_custom_field()`, `register_field()`, `validate_custom_mapping()` |
| Admin | `ProxyOwnerAdmin` | A deliberately minimal read surface: `record_key` (pk) + `proxy_owner_label` (`str(obj)`), registered via `config.admin`'s `register_both` / `register_platform_admin` / `register_tenant_admin` |
| Migration | `0001_proxy_owner_models` | Proxy registration only — zero tables |
| URLs / Celery / commands | none | This app has no `urls.py`, no tasks, and no management commands |

## Before you change this

- **Editing a proxy's fields is not possible here, and that is the whole point.**
  A proxy model cannot add or alter a column. If you need a new field on
  `RegionConfig`, it goes on the concrete model in `apps.siteconfig` with a
  migration in *that* app. A `makemigrations` run that proposes a real field
  change under `global_registries` means something has gone wrong — proxies are
  supposed to be `fields=[]` forever.
- **This app is in `SHARED_APPS` because `apps.compliance` needs it.** The
  settings comment at `settings.py:3889` is explicit: "Proxy-owner for
  `RegionConfig`; required by compliance." It is not in `SHARED_APPS` for its own
  sake — removing it from the list breaks compliance under schema-per-tenant.
  (Contrast `plans_entitlements` and `policies_rules`, which are absent from
  `SHARED_APPS` entirely and therefore not installed at all in that mode.)
- **The legacy imports dodge a circular import, deliberately.** `models.py`
  imports from `apps.siteconfig.models_global_experience` and
  `apps.siteconfig.models_platform_catalog` — the concrete submodules — never
  from `apps.siteconfig.models`. The in-file comment gives the reason: compliance
  (or another app) can load `global_registries` before `siteconfig.models` has
  finished loading. Rewriting these to the convenient top-level
  `from apps.siteconfig.models import ...` re-introduces the cycle.
- **`HolidayCalendar` proxies `apps.academics`, not siteconfig — and its table
  name lies about that.** The concrete model
  (`apps/academics/models_tenant_runtime.py`) pins `app_label = "academics"` but
  keeps `db_table = "siteconfig_holidaycalendar"`: it was extracted from
  siteconfig without a table rename. So the proxy sits in a different concrete
  app from its seven siblings while sharing their table prefix. That is why
  `0001_proxy_owner_models` depends on an `academics` migration. Do not infer the
  owning app from the `siteconfig_` prefix here.
- **`validate_custom_mapping` reports; it does not raise.** It returns
  `MappingValidation(ok, unmapped_keys, mapped)` and logs the counts — the
  *caller* is what fails the envelope by checking `ok`. The only thing in this
  module that raises `SchemaMappingError` is `register_field`, and only for an
  unknown `canonical_type`. If you are relying on an exception to stop a lossy
  transfer, there isn't one — check the return value.
- **A non-transferable field is reported as *unmapped*, and that is the
  mechanism.** `validate_custom_mapping` defaults to `transferable_only=True`, so
  `medical.allergies` (`pii=True, transferable=False`) lands in `unmapped_keys`
  even though it maps perfectly well. That is how PII is kept out of transfer
  envelopes. Passing `transferable_only=False` disables that protection — know
  why you are doing it.
- **`_CORE_FIELDS` is described in-code as "minimal … extended via `register_field`
  at app start."** Treat the tuple as a floor, not the complete registry; read
  the registration calls before concluding a field is unmapped.
- **Field-name matching is heuristic and dictionary-driven.** `map_custom_field`
  normalizes a name to snake_case and looks it up in `_HEURISTIC_HINTS` — a fixed
  dict (`dob`/`birthdate`/`date_of_birth` → `identity.date_of_birth`, and so on).
  There is no fuzzy matching. A tenant field the dict has never heard of is
  unmapped no matter how obvious its meaning looks to a human; teaching it a new
  spelling means adding a hint.
