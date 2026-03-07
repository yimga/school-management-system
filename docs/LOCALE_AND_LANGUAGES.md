# Locale and 100+ languages (i18n)

**Goal:** UI and content support for many locales; scale to 100+ languages via process and tooling.

## Current setup

- **Django i18n:** `USE_I18N = True`, `LocaleMiddleware` in `MIDDLEWARE`, `LANGUAGE_CODE` and `LANGUAGES` in settings.
- **Language switcher:** `path('i18n/setlang/', set_language, name='set_language')` (Django built-in). POST with `language` and `next` to switch.
- **LOCALE_PATHS:** `BASE_DIR / 'locale'`. Run `python manage.py makemessages -l <code>` to extract strings; add/edit `.po` files; `compilemessages` for `.mo`.
- **Registered languages (examples):** en, fr, pid, sw, ha, yo (see `LANGUAGES` and `EXTRA_LANG_INFO` in settings).
- **RTL:** Handled via `RegionConfig.is_rtl` and front-end; language code can drive RTL when needed.

## Adding more languages (100+ workflow)

1. **Extract:** `python manage.py makemessages -l <code>` (e.g. `ar`, `es`, `pt_BR`). Creates/updates `locale/<code>/LC_MESSAGES/django.po`.
2. **Translate:** Use Weblate/Crowdin, or edit `.po` manually, or export to CSV → translate → import.
3. **Register:** Add `('<code>', 'Display Name')` to `LANGUAGES` in settings. For custom codes (e.g. pid), add entry to `EXTRA_LANG_INFO` so `get_language_info()` works.
4. **Compile:** `python manage.py compilemessages`.
5. **Repeat** for each new language; use translation memory to speed up. No single technical blocker for 100+; scale is process and tooling.

## Frontend

- For JS-driven UIs, use the same locale keys or a small i18n layer that loads a JSON per language (e.g. `locale/<code>.json`). Keep existing RTL handling.
