#!/usr/bin/env bash
# Regenerate docs/architecture artifacts: migrations, apps list, URLs.
# Run from repo root. Optional: requires Django env (manage.py).

set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "[regen] Writing showmigrations to docs/architecture/migrations.txt"
python manage.py showmigrations > docs/architecture/migrations.txt 2>/dev/null || true

echo "[regen] Writing INSTALLED_APPS to docs/architecture/apps.txt"
python manage.py shell -c "
from django.conf import settings
apps = getattr(settings, 'INSTALLED_APPS', [])
with open('docs/architecture/apps.txt', 'w') as f:
    f.write('# Django INSTALLED_APPS (from config/settings.py)\n\n')
    for a in apps:
        f.write(a + '\n')
" 2>/dev/null || true

echo "[regen] Writing URL map to docs/architecture/urls.txt"
python manage.py show_urls 2>/dev/null > docs/architecture/urls.txt || true

echo "[regen] Done. Optional: python manage.py graph_models -a -o docs/architecture/models.png (requires django-extensions + graphviz)"
exit 0
