#!/usr/bin/env bash
# Admin-only abrupt-end sweep (P3): all admin_changelist routes from control_plane_sweep_routes.json.
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ -n "${VISUAL_QA_PYTHON:-}" ]]; then
  PYTHON_CMD="${VISUAL_QA_PYTHON}"
elif [[ -x "${ROOT}/.venv/bin/python" ]]; then
  PYTHON_CMD="${ROOT}/.venv/bin/python"
else
  PYTHON_CMD="python"
fi

PORT="${VISUAL_QA_PORT:-8012}"
MANAGER_HOST="${VISUAL_QA_MANAGER_HOST:-manager.runmycampus.com}"
ARTIFACT_DIR="${VISUAL_QA_ARTIFACT_DIR:-artifacts/admin-platform-proof}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"
VISUAL_USERNAME="${VISUAL_QA_USERNAME:-visualqa_admin}"
VISUAL_PASSWORD="${VISUAL_QA_PASSWORD:-VisualQaPass123!}"

mkdir -p "$ARTIFACT_DIR" artifacts

export SWEEP_TIER="${SWEEP_TIER:-admin_changelist}"
export SWEEP_PATHS="${SWEEP_PATHS:-/admin/}"
export SWEEP_INCLUDE_TENANT="${SWEEP_INCLUDE_TENANT:-0}"
export SWEEP_SKIP_HEALTH="${SWEEP_SKIP_HEALTH:-0}"
export SWEEP_HEALTH_SECS="${SWEEP_HEALTH_SECS:-120}"
export MANAGER_BASE_URL="http://${MANAGER_HOST}:${PORT}"
export VISUAL_QA_MANAGER_HOST="$MANAGER_HOST"
export VISUAL_QA_PORT="$PORT"
export VISUAL_QA_USERNAME="$VISUAL_USERNAME"
export VISUAL_QA_PASSWORD="$VISUAL_PASSWORD"
export PLAYWRIGHT_HOST_RULES="MAP ${MANAGER_HOST} 127.0.0.1"

"${PYTHON_CMD}" scripts/generate_control_plane_sweep_routes.py --write

if [[ ! -f "node_modules/playwright/cli.js" ]]; then
  echo "run_admin_abrupt_end_sweep: run npm ci first." >&2
  exit 1
fi

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

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if [[ "${SWEEP_SKIP_HEALTH:-0}" == "1" ]] && curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/-/version/" | grep -q '^200$'; then
  seed_qa_user
else
  if ! curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/-/version/" | grep -q '^200$'; then
    "${PYTHON_CMD}" manage.py migrate --noinput
    seed_qa_user
    nohup env SECURE_SSL_REDIRECT=0 DEBUG=1 CSRF_COOKIE_SECURE=0 SESSION_COOKIE_SECURE=0 \
      CSRF_TRUSTED_ORIGINS="http://127.0.0.1:${PORT},http://${MANAGER_HOST}:${PORT}" \
      "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
    SERVER_PID="$!"
    code=""
    for _ in $(seq 1 60); do
      code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${MANAGER_HOST}" -H 'Accept: application/json' "http://127.0.0.1:${PORT}/-/version/" || true)"
      [[ "$code" == "200" ]] && break
      sleep 2
    done
    if [[ "${code:-}" != "200" ]]; then
      echo "run_admin_abrupt_end_sweep: server not ready (HTTP ${code:-none})." >&2
      tail -n 40 "$RUNSERVER_LOG" >&2 || true
      exit 1
    fi
  else
    seed_qa_user
  fi
fi

if [[ -f scripts/seed_manager_playwright_auth.js ]]; then
  node scripts/seed_manager_playwright_auth.js || true
fi

node scripts/verify_platform_abrupt_end_sweep.mjs
