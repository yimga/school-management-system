# i18n: makemessages and translatable strings (World Engine)

Django’s translation framework is used for UI strings. All user-facing text should be wrapped so it can be extracted and translated.

## Extract strings

1. **Requirement:** GNU gettext on the host (`msguniq`, `xgettext`). On Windows use WSL or a gettext build; on macOS: `brew install gettext`.
2. **Extract:**  
   `python manage.py makemessages -l en`  
   Use `-a` to update existing `.po` files (e.g. after adding new `_()` or `{% trans %}`).
3. **Compile:**  
   `python manage.py compilemessages`  
   Produces `.mo` files used at runtime.

## Where strings live

- **Locale:** `locale/<lang>/LC_MESSAGES/django.po` (e.g. `locale/en/LC_MESSAGES/django.po`).
- **Settings:** `LOCALE_PATHS` in `config/settings.py` should include the project `locale` directory.

## Wrapping strings

- **Python:** `from django.utils.translation import gettext as _` then `_("Your string")`.
- **Templates:** `{% load i18n %}` then `{% trans "Your string" %}` or `{{ _("Your string") }}` in some setups.
- **No hardcoded UI:** Avoid raw user-facing strings in Python or templates; use `_()` or `{% trans %}` so they appear in `.po` and can be translated.

## CI (optional)

Add a step that runs `makemessages -l en -a` and `compilemessages` when i18n files or code change, and fails if new strings in code are not present in `.po` (e.g. compare `git diff` on `.po` after running makemessages).

## Reference

- [Django i18n](https://docs.djangoproject.com/en/stable/topics/i18n/).
- World Engine verification: `docs/WORLD_ENGINE_VERIFICATION.md` — i18n row.
