#!/usr/bin/env bash
# Manager /super/ ↔ /admin/ surface parity Playwright + matrix verifier.
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
MANAGER_HOST="${VISUAL_QA_MANAGER_HOST:-manager.runmycampus.com}"
ARTIFACT_DIR="${VISUAL_QA_ARTIFACT_DIR:-artifacts/manager-surface-parity}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"
VISUAL_USERNAME="${VISUAL_QA_USERNAME:-visualqa_admin}"
VISUAL_PASSWORD="${VISUAL_QA_PASSWORD:-VisualQaPass123!}"

mkdir -p "$ARTIFACT_DIR" artifacts
rm -f artifacts/manager-playwright-auth.json

# Verifiers use Django test client against the default DB — migrate first.
"${PYTHON_CMD}" manage.py migrate --noinput

if [[ ! -f "node_modules/playwright/cli.js" ]]; then
  echo "run_manager_surface_parity: run npm ci first." >&2
  exit 1
fi

"${PYTHON_CMD}" scripts/verify_theme_visibility_platform.py
"${PYTHON_CMD}" scripts/verify_backend_base_shell_routing.py
"${PYTHON_CMD}" scripts/verify_platform_chrome_shell_coverage.py
"${PYTHON_CMD}" scripts/verify_platform_chrome_sweep.py
"${PYTHON_CMD}" scripts/verify_platform_surface_layout_contract.py
"${PYTHON_CMD}" scripts/verify_page_fold_standards.py
"${PYTHON_CMD}" scripts/verify_manager_admin_cp_layout.py
"${PYTHON_CMD}" scripts/verify_super_admin_surface_parity.py --write
"${PYTHON_CMD}" manage.py test \
  apps.schools.tests.test_super_admin_surface_parity.SuperAdminSurfaceParityTests.test_manager_admin_index_renders_backoffice_content \
  --verbosity=1 --no-input

seed_qa_user() {
  "${PYTHON_CMD}" - <<PY
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
u, _ = User.objects.get_or_create(
    username="${VISUAL_USERNAME}",
    defaults={
        "is_staff": True,
        "is_superuser": True,
        "role": "SUPERADMIN",
    },
)
u.is_staff = True
u.is_superuser = True
u.role = "SUPERADMIN"
u.set_password("${VISUAL_PASSWORD}")
u.save()
print(f"Seeded manager QA user: {u.username}")
PY
}

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ "${MANAGER_SURFACE_FRESH_SERVER:-0}" != "1" ]] && curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/-/version/" | grep -q '^200$'; then
  echo "[run_manager_surface_parity] Reusing server on port ${PORT} (seeding QA user on default DB)"
  seed_qa_user
else
  if curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/-/version/" | grep -q '^200$'; then
    echo "[run_manager_surface_parity] Port ${PORT} busy; set MANAGER_SURFACE_FRESH_SERVER=0 to reuse or free the port." >&2
  fi
  "${PYTHON_CMD}" manage.py migrate --noinput
  seed_qa_user
  nohup env SECURE_SSL_REDIRECT=0 DEBUG=1 CSRF_COOKIE_SECURE=0 SESSION_COOKIE_SECURE=0 \
    CSRF_TRUSTED_ORIGINS="http://127.0.0.1:${PORT},http://${MANAGER_HOST}:${PORT}" \
    "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
  SERVER_PID="$!"
  for _ in $(seq 1 45); do
    code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" -H 'Accept: application/json' "http://127.0.0.1:${PORT}/-/version/" || true)"
    [[ "$code" == "200" ]] && break
    sleep 2
  done
  if [[ "${code:-}" != "200" ]]; then
    echo "run_manager_surface_parity: server not ready (HTTP ${code:-none})." >&2
    tail -n 40 "$RUNSERVER_LOG" >&2 || true
    exit 1
  fi
fi

export MANAGER_BASE_URL="http://${MANAGER_HOST}:${PORT}"
export VISUAL_QA_MANAGER_HOST="$MANAGER_HOST"
export VISUAL_QA_PORT="$PORT"
export VISUAL_QA_USERNAME="$VISUAL_USERNAME"
export VISUAL_QA_PASSWORD="$VISUAL_PASSWORD"
export PLAYWRIGHT_HOST_RULES="MAP ${MANAGER_HOST} 127.0.0.1"

node scripts/seed_manager_playwright_auth.js

node node_modules/playwright/cli.js test \
  tests/e2e/manager-surface-parity.spec.js \
  tests/e2e/manager-theme-visibility.spec.js \
  tests/e2e/studio-os-manager-ux.spec.js \
  --workers=1 --reporter=line
