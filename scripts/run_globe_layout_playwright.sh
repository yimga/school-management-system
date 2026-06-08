#!/usr/bin/env bash
# Globe layout Playwright — migrate DB, seed auth, run control-plane-layout-audit (batch 1651).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export MSYS_NO_PATHCONV=1

# Isolated DB so migrate + runserver share one file (Windows %TEMP% drift breaks Playwright).
export DB_FILE="${DB_FILE:-${ROOT_DIR}/db_playwright_globe.sqlite3}"

if [[ -n "${VISUAL_QA_PYTHON:-}" ]]; then
  PYTHON_CMD="${VISUAL_QA_PYTHON}"
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_CMD="${ROOT_DIR}/.venv/bin/python"
else
  PYTHON_CMD="python"
fi

PORT="${VISUAL_QA_PORT:-8012}"
MANAGER_HOST="${VISUAL_QA_MANAGER_HOST:-manager.runmycampus.com}"
export VISUAL_QA_PORT="$PORT"
export MANAGER_BASE_URL="${MANAGER_BASE_URL:-http://${MANAGER_HOST}:${PORT}}"
export VISUAL_QA_USERNAME="${VISUAL_QA_USERNAME:-admin}"
export VISUAL_QA_PASSWORD="${VISUAL_QA_PASSWORD:-Sch00l_1234}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-$VISUAL_QA_PASSWORD}"
export VISUAL_QA_PYTHON="$PYTHON_CMD"
export E2E_LOGIN_USER="$VISUAL_QA_USERNAME"

ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/globe-layout-playwright}"
mkdir -p "$ARTIFACT_DIR"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

echo "globe-layout-playwright: migrate"
"$PYTHON_CMD" manage.py migrate --noinput

echo "globe-layout-playwright: ensure superuser"
"$PYTHON_CMD" manage.py ensure_superuser --no-input --password "$VISUAL_QA_PASSWORD" 2>/dev/null || true

echo "globe-layout-playwright: seed e2e TOTP for manager login (MFA verify, not setup)"
"$PYTHON_CMD" - <<PY
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.contrib.auth import get_user_model
User = get_user_model()
username = os.environ.get("VISUAL_QA_USERNAME", "admin")
password = os.environ.get("VISUAL_QA_PASSWORD", "Sch00l_1234")
u = User.objects.filter(username=username).first()
if not u:
    u = User.objects.create(username=username, is_staff=True, is_superuser=True, role="SUPERADMIN")
u.is_staff = True
u.is_superuser = True
u.role = "SUPERADMIN"
u.set_password(password)
u.save()
try:
    from django_otp.plugins.otp_totp.models import TOTPDevice
    TOTPDevice.objects.filter(user=u).delete()
    device, _ = TOTPDevice.objects.update_or_create(
        user=u, name="e2e-playwright", defaults={"confirmed": True}
    )
    device.key = os.environ.get(
        "VISUAL_QA_TOTP_HEX_KEY",
        "eab95095c004f245721ba0fa7ebf82d5dc73",
    )
    device.save()
    print(f"Seeded TOTP e2e-playwright for {u.username}")
except Exception as exc:
    print(f"WARN: TOTP seed skipped: {exc}")
PY

echo "globe-layout-playwright: starting Django on ${MANAGER_BASE_URL}"
"$PYTHON_CMD" manage.py runserver "0.0.0.0:${PORT}" >"$RUNSERVER_LOG" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 90); do
  code=$(curl -sf -o /dev/null -w "%{http_code}" -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/authentication/login/" || echo "000")
  if [[ "$code" == "200" ]]; then
    break
  fi
  sleep 2
done

sleep 5

echo "globe-layout-playwright: seed manager auth"
node scripts/seed_manager_playwright_auth.js

echo "globe-layout-playwright: Playwright control-plane-layout-audit"
npx playwright test tests/e2e/control-plane-layout-audit.spec.js --project=manager-chromium --workers=1

echo "GLOBE_LAYOUT_PLAYWRIGHT_PASS"
