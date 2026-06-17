#!/usr/bin/env bash
# Web entrypoint for self-hosted RunMyCampus. Applies migrations (django-tenants
# aware), then starts gunicorn via the project's resource-aware config. Lean by
# design — heavy first-run seeding (seed_render_users, platform catalogs, etc.)
# is operator-driven; see docs/SELF_HOST_MIGRATION.md and render_predeploy.sh.
set -euo pipefail
cd /app

echo "[selfhost] waiting for database..."
python - <<'PY'
import os, time, sys
import psycopg2
url = os.environ.get("DATABASE_URL", "")
for attempt in range(60):
    try:
        psycopg2.connect(url).close()
        print("[selfhost] database is up")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 - boot-time readiness poll
        time.sleep(2)
print("[selfhost] database not reachable after 120s", file=sys.stderr)
sys.exit(1)
PY

if [[ "${USE_DJANGO_TENANTS:-1}" == "1" ]]; then
  echo "[selfhost] migrate_schemas --shared"
  python manage.py migrate_schemas --shared --noinput
  python manage.py ensure_tenant_schemas || true
  echo "[selfhost] migrate_schemas --tenant"
  python manage.py migrate_schemas --tenant --noinput
else
  echo "[selfhost] migrate"
  python manage.py migrate --noinput
fi

echo "[selfhost] starting gunicorn"
exec gunicorn -c config/gunicorn.conf.py config.wsgi:application
