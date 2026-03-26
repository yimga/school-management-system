# Django gettext catalogs (`locale/`)

- **Merge full template/Python string inventory:**  
  `python manage.py sync_i18n_catalog`  
  Writes `locale/<lang>/LC_MESSAGES/django.po` for every `LANGUAGES` entry in `config/settings.py`.

- **Compile binary catalogs (no `msgfmt` required):**  
  `python manage.py sync_i18n_catalog --compile`  
  Refreshes `django.mo` via **polib**.

- **Dry-run (counts only):**  
  `python manage.py sync_i18n_catalog --dry-run`

- **Prune entries removed from codebase (destructive):**  
  `python manage.py sync_i18n_catalog --prune-stale --compile`  
  Drops `.po` rows whose `msgid` no longer appears in the scan (review before committing).

- **CI / pre-deploy drift check:**  
  `python scripts/verify_i18n_catalog_fresh.py`  
  Exits non-zero if any scanned string is missing from `locale/en/LC_MESSAGES/django.po`. Optional: `--warn-stale` / `--strict-stale`.

Extraction lives in `apps/siteconfig/i18n_catalog_builder.py`: AST for Python; regex for `{% trans %}`, `{% blocktrans %}`, `{{ _('…') }}`; narrow patterns for `gettext` / `ngettext` in `static/**/*.js` (vendor dirs skipped). GNU **xgettext** remains optional for `djangojs` or richer JS.

**JSON packs** under `locale/translations/*.json` are separate from `django.po`; keep them aligned per product workflow.

See [RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md](../docs/RUNMYCAMPUS_SINGLE_EXECUTION_SOURCE_OF_TRUTH.md) (N21 / i18n).
