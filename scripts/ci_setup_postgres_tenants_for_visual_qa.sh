#!/usr/bin/env bash
# Minimal Postgres + django-tenants bootstrap for Playwright tenant-host tests.
# Used by .github/workflows/playwright-tenant-postgres.yml (not the SQLite pre_deploy_gate).
#
# Requires: DATABASE_URL (postgresql), MULTI_TENANT_BASE_DOMAIN (e.g. runmycampus.com),
#           SECRET_KEY, Django settings that enable schema tenants on PostgreSQL.
# Optional: ADMIN_PASSWORD — passed to seed_render_users for teacher1 / Parent1 (align with VISUAL_QA_TENANT_PASSWORD).
# Optional skips: CI_VISUAL_QA_SKIP_BACKFILL_SCHOOLDOMAIN=1, CI_VISUAL_QA_SKIP_TENANT_RUNTIME_CHECK=1
# Optional wait tuning: CI_VISUAL_QA_DB_WAIT_ATTEMPTS (default 45), CI_VISUAL_QA_DB_WAIT_SLEEP (default 2)
#
# After this script, scripts/run_visual_qa.sh probes the first tenant Domain and sets CSRF_TRUSTED_ORIGINS
# (including that host) before starting runserver so tenant portal logins are not CSRF-blocked.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${VENV_PYTHON:-.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python"
fi

run() {
  echo "[ci_visual_qa_db] $*"
  "$@"
}

"${PYTHON_BIN}" -c "import sys; print('[ci_visual_qa_db] Python', sys.version.split()[0])"

if [[ -z "${DATABASE_URL:-}" ]] || [[ "${DATABASE_URL}" != postgresql* ]]; then
  echo "[ci_visual_qa_db] DATABASE_URL must be set to a postgresql:// URL." >&2
  exit 1
fi

wait_for_postgres() {
  local max_attempts="${CI_VISUAL_QA_DB_WAIT_ATTEMPTS:-45}"
  local sleep_s="${CI_VISUAL_QA_DB_WAIT_SLEEP:-2}"
  local attempt=1
  while [[ "$attempt" -le "$max_attempts" ]]; do
    if "${PYTHON_BIN}" - <<'PY'
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db import connections

try:
    connections["default"].ensure_connection()
except Exception as exc:
    print("[ci_visual_qa_db] DB not ready:", exc, file=sys.stderr)
    sys.exit(1)
sys.exit(0)
PY
    then
      echo "[ci_visual_qa_db] PostgreSQL is accepting connections."
      return 0
    fi
    echo "[ci_visual_qa_db] waiting for PostgreSQL (attempt ${attempt}/${max_attempts})..."
    sleep "$sleep_s"
    attempt=$((attempt + 1))
  done
  echo "[ci_visual_qa_db] ERROR: timed out waiting for PostgreSQL." >&2
  exit 1
}

wait_for_postgres

run "${PYTHON_BIN}" manage.py migrate_schemas --shared --noinput
run "${PYTHON_BIN}" manage.py ensure_tenant_schemas
run "${PYTHON_BIN}" manage.py migrate_schemas --tenant --noinput
run "${PYTHON_BIN}" manage.py migrate_schools_to_tenants
run "${PYTHON_BIN}" manage.py migrate_schemas --tenant --noinput

# Align with scripts/release/render_predeploy.sh (idempotent; avoids sparse SchoolDomain / routing gaps).
if [[ "${CI_VISUAL_QA_SKIP_BACKFILL_SCHOOLDOMAIN:-0}" != "1" ]]; then
  run "${PYTHON_BIN}" manage.py backfill_schooldomain
fi
if [[ "${CI_VISUAL_QA_SKIP_TENANT_RUNTIME_CHECK:-0}" != "1" ]]; then
  run "${PYTHON_BIN}" manage.py check_tenant_runtime
fi

# Tenant demo users for ux-visual-qa.spec.js (teacher1, Parent1, principal1)
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-VisualQaPass123!}"
run "${PYTHON_BIN}" manage.py seed_render_users

# Fail fast if Playwright would skip tenant tests (no customers.Domain / wrong base domain).
run "${PYTHON_BIN}" - <<'PY'
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django

django.setup()

from django.db import connection

if connection.vendor != "postgresql":
    print("[ci_visual_qa_db] ERROR: expected PostgreSQL after setup.", file=sys.stderr)
    sys.exit(1)

from apps.customers.models import Client, Domain

c = Client.objects.exclude(schema_name="public").order_by("id").first()
if not c:
    print("[ci_visual_qa_db] ERROR: no tenant Client; migrations/seed incomplete.", file=sys.stderr)
    sys.exit(1)

d = Domain.objects.filter(tenant=c).order_by("id").values_list("domain", flat=True).first()
if not d:
    print("[ci_visual_qa_db] ERROR: no Domain for tenant; check MULTI_TENANT_BASE_DOMAIN and migrate_schools_to_tenants.", file=sys.stderr)
    sys.exit(1)

print("[ci_visual_qa_db] tenant domain OK:", d)
PY

echo "[ci_visual_qa_db] done"
