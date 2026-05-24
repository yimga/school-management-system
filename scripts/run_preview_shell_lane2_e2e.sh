#!/usr/bin/env bash
# Preview Shell 100x Lane 2 — manager host Playwright (batch 1485).
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
export VISUAL_QA_PORT="$PORT"
export MANAGER_BASE_URL="${MANAGER_BASE_URL:-http://${MANAGER_HOST}:${PORT}}"
export VISUAL_QA_USERNAME="${VISUAL_QA_USERNAME:-admin}"
export VISUAL_QA_PASSWORD="${VISUAL_QA_PASSWORD:-Sch00l_1234}"
export ADMIN_PASSWORD="${ADMIN_PASSWORD:-$VISUAL_QA_PASSWORD}"

ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/preview-shell-lane2}"
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

echo "preview-shell-lane2: seed render users (admin + demo tenants)"
"$PYTHON_CMD" manage.py seed_render_users 2>/dev/null || true
"$PYTHON_CMD" manage.py ensure_superuser --no-input --password "$VISUAL_QA_PASSWORD" 2>/dev/null || true

echo "preview-shell-lane2: starting Django on ${MANAGER_BASE_URL}"
"$PYTHON_CMD" manage.py runserver "0.0.0.0:${PORT}" >"$RUNSERVER_LOG" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 60); do
  if curl -sf -o /dev/null -H "Host: ${MANAGER_HOST}" "http://127.0.0.1:${PORT}/authentication/login/"; then
    break
  fi
  sleep 1
done

echo "preview-shell-lane2: seed manager auth state"
node scripts/seed_manager_playwright_auth.js

echo "preview-shell-lane2: Playwright"
npx playwright test tests/e2e/preview-shell-parity.spec.js --reporter=line

echo "preview-shell-lane2: PREVIEW_SHELL_LANE2_E2E_PASS"
