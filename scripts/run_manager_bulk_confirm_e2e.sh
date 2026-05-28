#!/usr/bin/env bash
# Playwright: manager bulk <dialog> confirm flow + apply_purge bulk guard verifier.
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

PORT="${VISUAL_QA_PORT:-8000}"
MANAGER_HOST="${VISUAL_QA_MANAGER_HOST:-manager.runmycampus.com}"
ARTIFACT_DIR="${VISUAL_QA_ARTIFACT_DIR:-artifacts/manager-bulk-confirm-e2e}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"
VISUAL_USERNAME="${VISUAL_QA_USERNAME:-visualqa_admin}"
VISUAL_PASSWORD="${VISUAL_QA_PASSWORD:-VisualQaPass123!}"

E2E_SESSION_ENV=(
  REDIS_URL=
  RMC_FORCE_DB_SESSIONS=1
)
# Align DB + sessions with export script (skip 0-byte placeholder sqlite files).
_e2e_db_file() {
  local candidate="$1"
  if [[ -f "$candidate" ]] && [[ "$(wc -c <"$candidate" | tr -d ' ')" -gt 4096 ]]; then
    echo "$candidate"
  fi
}
if _db="$(_e2e_db_file "${ROOT_DIR}/db_working.sqlite3")"; then
  E2E_SESSION_ENV+=(DB_FILE="${_db}")
elif _db="$(_e2e_db_file "${ROOT_DIR}/db.sqlite3")"; then
  E2E_SESSION_ENV+=(DB_FILE="${_db}")
fi

mkdir -p "$ARTIFACT_DIR" artifacts
rm -f artifacts/manager-playwright-auth.json

env "${E2E_SESSION_ENV[@]}" "${PYTHON_CMD}" manage.py migrate --noinput
env "${E2E_SESSION_ENV[@]}" "${PYTHON_CMD}" manage.py ensure_superuser --password "${VISUAL_PASSWORD}" --no-input 2>/dev/null || true
env "${E2E_SESSION_ENV[@]}" "${PYTHON_CMD}" scripts/verify_bulk_school_actions_no_apply_purge.py

if [[ ! -f "node_modules/playwright/cli.js" ]]; then
  echo "run_manager_bulk_confirm_e2e: run npm ci first." >&2
  exit 1
fi

seed_qa_user() {
  "${PYTHON_CMD}" - <<PY
import os
os.environ["REDIS_URL"] = ""
os.environ["RMC_FORCE_DB_SESSIONS"] = "1"
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
try:
    from django_otp.plugins.otp_totp.models import TOTPDevice

    TOTPDevice.objects.filter(user=u).delete()
    device, _ = TOTPDevice.objects.update_or_create(
        user=u,
        name="e2e-playwright",
        defaults={"confirmed": True},
    )
    # django-otp stores TOTP key as hex (see TOTPDevice.bin_key).
    device.key = os.environ.get(
        "VISUAL_QA_TOTP_HEX_KEY",
        "eab95095c004f245721ba0fa7ebf82d5dc73",
    )
    device.save()
except Exception:
    pass
from apps.platform_runtime.models_operator_identity import PlatformOperatorProfile
from apps.platform_runtime.operator_identity import ensure_platform_operator_profile
from apps.schools.models import School

ensure_platform_operator_profile(u, tier="break_glass")
peer, _ = User.objects.get_or_create(
    username="e2e_bulk_operator_peer",
    defaults={
        "is_staff": True,
        "is_superuser": True,
        "role": "SUPERADMIN",
        "email": "e2e-bulk-operator-peer@runmycampus.test",
    },
)
peer.is_staff = True
peer.is_superuser = True
peer.role = "SUPERADMIN"
peer.is_active = True
peer.save()
ensure_platform_operator_profile(peer, tier="support")
PlatformOperatorProfile.objects.filter(user=peer).update(
    status=PlatformOperatorProfile.Status.ACTIVE
)
print("Seeded e2e_bulk_operator_peer for team bulk roster")

if not School.objects.filter(is_active=True).exists():
    School.objects.create(
        name="E2E Bulk Schools Fixture",
        slug="e2e-bulk-schools",
        subdomain="e2ebulk",
        is_active=True,
        is_approved=True,
    )
    print("Seeded e2e-bulk-schools fixture")
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

free_port() {
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${PORT}/tcp" 2>/dev/null || true
    return
  fi
  if command -v netstat >/dev/null 2>&1; then
    while read -r pid; do
      [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true
    done < <(netstat -ano 2>/dev/null | grep ":${PORT} " | grep LISTENING | awk '{print $NF}' | sort -u)
  fi
  sleep 1
}

if [[ "${MANAGER_BULK_FRESH_SERVER:-1}" != "1" ]] && curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/-/version/" | grep -q '^200$'; then
  echo "[run_manager_bulk_confirm_e2e] Reusing server on port ${PORT}"
  seed_qa_user
else
  if [[ "${MANAGER_BULK_FRESH_SERVER:-1}" == "1" ]]; then
    free_port
  elif curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/-/version/" | grep -q '^200$'; then
    echo "[run_manager_bulk_confirm_e2e] Port ${PORT} busy; set MANAGER_BULK_FRESH_SERVER=1 or free the port." >&2
    exit 1
  fi
  seed_qa_user
  # DB sessions only — cache sessions are per-process and break Playwright storage export.
  nohup env "${E2E_SESSION_ENV[@]}" SECURE_SSL_REDIRECT=0 DEBUG=1 CSRF_COOKIE_SECURE=0 SESSION_COOKIE_SECURE=0 \
    CSRF_TRUSTED_ORIGINS="http://127.0.0.1:${PORT},http://${MANAGER_HOST}:${PORT}" \
    "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
  SERVER_PID="$!"
  for _ in $(seq 1 45); do
    code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" -H 'Accept: application/json' "http://127.0.0.1:${PORT}/-/version/" || true)"
    [[ "$code" == "200" ]] && break
    sleep 2
  done
  if [[ "${code:-}" != "200" ]]; then
    echo "run_manager_bulk_confirm_e2e: server not ready (HTTP ${code:-none})." >&2
    tail -n 40 "$RUNSERVER_LOG" >&2 || true
    exit 1
  fi
fi

export MANAGER_BASE_URL="http://${MANAGER_HOST}:${PORT}"
export VISUAL_QA_MANAGER_HOST="$MANAGER_HOST"
export VISUAL_QA_PORT="$PORT"
export VISUAL_QA_USERNAME="$VISUAL_USERNAME"
export VISUAL_QA_PASSWORD="$VISUAL_PASSWORD"
export VISUAL_QA_PYTHON="${PYTHON_CMD}"
export DJANGO_LOG_LEVEL="${DJANGO_LOG_LEVEL:-CRITICAL}"
export PLAYWRIGHT_HOST_RULES="MAP ${MANAGER_HOST} 127.0.0.1"

export MANAGER_PLAYWRIGHT_HTTP_PROBE=1
env "${E2E_SESSION_ENV[@]}" "${PYTHON_CMD}" scripts/export_manager_playwright_storage.py
node scripts/probe_manager_playwright_auth.js

node node_modules/playwright/cli.js test \
  tests/e2e/manager-bulk-confirm-dialog.spec.js \
  --project=manager-chromium \
  --workers=1 --reporter=line

"${PYTHON_CMD}" scripts/run_sqlite_memory_tests.py \
  apps.schools.tests.test_bulk_operator_actions \
  apps.schools.tests.test_super_bulk_api_http \
  --verbosity=1
