# apps/locale

> Localization helpers that keep tenant-facing input and copy out of the
> Cameroon-only default state: per-country phone placeholders + dial codes, and
> the compiled translation catalogs the platform ships.

**Type:** support library — **not** an installed Django app. It has no models, no
schema, and no `AppConfig`, and it does not appear in `INSTALLED_APPS`. It is a
lookup/asset package imported by forms, context processors, and the localization
service.

## What this app owns

`locale` owns the small, boring, load-bearing pieces of localization that would
otherwise get hardcoded to one market. `phone_formats.py` maps an ISO 3166-1
alpha-2 country code to its dial code and an input placeholder (for example `CM →
+237 6XX XXX XXX`, `NG → +234 8XX XXX XXXX`), with a neutral international
fallback (`+CC NNN NNN NNNN`) for any corridor not yet enumerated — so a phone
field in a Nigerian or Kenyan school does not display a Cameroonian hint. The
`translations/` subtree carries translation assets that sit alongside Django's
own `locale/` `.po`/`.mo` catalogs.

This package is deliberately data-first and dependency-light: it is safe to import
from a form's `__init__` or a context processor without pulling in models or
triggering database access.

## Key modules

| Module | Purpose |
| --- | --- |
| `phone_formats.py` | `PHONE_FORMATS` (ISO2 → dial code + placeholder) and `phone_placeholder()`; neutral fallback when the country is not enumerated. |
| `translations/` | Translation assets shipped with the platform. |

## Before you change this

- **Lookups are keyed by ISO 3166-1 alpha-2, upper-cased.** Keep new entries in
  that form; `phone_placeholder(None)` and unknown codes must keep returning the
  neutral international placeholder, never raise.
- **This package must stay import-safe and side-effect-free.** It is imported on
  form construction and request context building — no model imports, no DB access,
  no network at import time.
- **Adding a country is additive.** Extend `PHONE_FORMATS`; never remove or
  repurpose an existing corridor's placeholder, since form widgets and saved
  fixtures reference the shape.
