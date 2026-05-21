#!/usr/bin/env bash
# Lane 2 — Playwright dual-plane theme experience (manager platform + tenant school).
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

PORT="${VISUAL_QA_PORT:-8014}"
MANAGER_HOST="${VISUAL_QA_MANAGER_HOST:-manager.runmycampus.com}"
TENANT_HOST="${TENANT_E2E_HOST:-apple-class-qa.runmycampus.com}"
TENANT_SLUG="${TENANT_E2E_SLUG:-apple-class-qa}"
ARTIFACT_DIR="${VISUAL_QA_ARTIFACT_DIR:-artifacts/theme-experience-dual-plane}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"

VISUAL_USERNAME="${VISUAL_QA_USERNAME:-visualqa_admin}"
VISUAL_PASSWORD="${VISUAL_QA_PASSWORD:-VisualQaPass123!}"
TENANT_USERNAME="${E2E_USERNAME:-${APPLE_QA_TENANT_USERNAME:-appleqa_tenant}}"
TENANT_PASSWORD="${E2E_PASSWORD:-${APPLE_QA_TENANT_PASSWORD:-AppleQaPass123!}}"

mkdir -p "$ARTIFACT_DIR" artifacts

if [[ ! -f "node_modules/playwright/cli.js" ]]; then
  echo "run_theme_experience_dual_plane_e2e: run npm ci first." >&2
  exit 1
fi

"${PYTHON_CMD}" manage.py migrate --noinput

echo "Seeding Apple-class QA tenant (MFA + settings.manage) …"
"${PYTHON_CMD}" scripts/seed_apple_class_qa.py

"${PYTHON_CMD}" scripts/verify_theme_experience_plane_isolation.py
"${PYTHON_CMD}" scripts/verify_dual_plane_theme_experience.py
"${PYTHON_CMD}" scripts/verify_portal_theme_token_spine.py

seed_manager_user() {
  "${PYTHON_CMD}" - <<PY
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
u, _ = User.objects.get_or_create(
    username="${VISUAL_USERNAME}",
    defaults={"is_staff": True, "is_superuser": True, "role": "SUPERADMIN"},
)
u.is_staff = True
u.is_superuser = True
u.role = "SUPERADMIN"
u.set_password("${VISUAL_PASSWORD}")
u.save()
print(f"Seeded manager QA user: {u.username}")
PY
}

seed_manager_user

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/-/version/" | grep -q '^200$'; then
  echo "[theme-dual-plane] Reusing server on port ${PORT}"
else
  nohup env SECURE_SSL_REDIRECT=0 DEBUG=1 CSRF_COOKIE_SECURE=0 SESSION_COOKIE_SECURE=0 \
    CSRF_TRUSTED_ORIGINS="http://127.0.0.1:${PORT},http://${MANAGER_HOST}:${PORT},http://${TENANT_HOST}:${PORT}" \
    ALLOWED_HOSTS="127.0.0.1,localhost,testserver,runmycampus.com,.runmycampus.com,${MANAGER_HOST},${TENANT_HOST}" \
    "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
  SERVER_PID="$!"
  code=""
  for _ in $(seq 1 45); do
    code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" -H 'Accept: application/json' "http://127.0.0.1:${PORT}/-/version/" || true)"
    [[ "$code" == "200" ]] && break
    sleep 2
  done
  if [[ "${code:-}" != "200" ]]; then
    echo "run_theme_experience_dual_plane_e2e: server not ready (HTTP ${code:-none})." >&2
    tail -n 40 "$RUNSERVER_LOG" >&2 || true
    exit 1
  fi
fi

export MANAGER_BASE_URL="http://${MANAGER_HOST}:${PORT}"
export TENANT_BASE_URL="http://${TENANT_HOST}:${PORT}"
export TENANT_E2E_HOST="${TENANT_HOST}"
export TENANT_E2E_SLUG="${TENANT_SLUG}"
export TENANT_LOGIN_URL="${TENANT_BASE_URL}/authentication/login/"
export BASE_URL="${MANAGER_BASE_URL}"
export VISUAL_QA_PORT="$PORT"
export VISUAL_QA_MANAGER_HOST="$MANAGER_HOST"
export VISUAL_QA_USERNAME="$VISUAL_USERNAME"
export VISUAL_QA_PASSWORD="$VISUAL_PASSWORD"
export E2E_USERNAME="$TENANT_USERNAME"
export E2E_PASSWORD="$TENANT_PASSWORD"
export APPLE_QA_TENANT_USERNAME="$TENANT_USERNAME"
export APPLE_QA_TENANT_PASSWORD="$TENANT_PASSWORD"
export PLAYWRIGHT_HOST_RULES="MAP ${MANAGER_HOST} 127.0.0.1,MAP ${TENANT_HOST} 127.0.0.1,MAP *.runmycampus.com 127.0.0.1"

node node_modules/playwright/cli.js test \
  tests/e2e/theme_experience_dual_plane.spec.js \
  tests/e2e/theme_experience_forensic.spec.js \
  --workers=1 \
  --reporter=line

echo "theme_experience_dual_plane_e2e: PASS"
