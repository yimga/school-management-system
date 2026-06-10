#!/usr/bin/env bash
# Boots Django for tenant phase1/phase2 Playwright (demo-school path tenant).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

if [[ -n "${VISUAL_QA_PYTHON:-}" ]]; then
  PYTHON_CMD="${VISUAL_QA_PYTHON}"
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_CMD="${ROOT_DIR}/.venv/bin/python"
else
  PYTHON_CMD="python"
fi

PORT="${VISUAL_QA_PORT:-8012}"
TENANT_SLUG="${TENANT_SLUG:-demo-school}"
PASSWORD="${E2E_TENANT_PASSWORD:-Test1234}"

export REDIS_URL=""
export RMC_FORCE_DB_SESSIONS=1
export SECURE_SSL_REDIRECT=0
export DEBUG=1
export CSRF_COOKIE_SECURE=0
export SESSION_COOKIE_SECURE=0

"$PYTHON_CMD" manage.py migrate --noinput
"$PYTHON_CMD" manage.py ensure_developer_sandbox_tenant --school-slug="$TENANT_SLUG" --password="$PASSWORD"
"$PYTHON_CMD" manage.py seed_demo_tenant_users --school-slug="$TENANT_SLUG" --password="$PASSWORD"
exec "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload
