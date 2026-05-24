#!/usr/bin/env bash
# Tenant portal Lane 2 — path-based Playwright (any TENANT_SLUG on 127.0.0.1).
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"
export MSYS_NO_PATHCONV=1

if [[ -n "${VISUAL_QA_PYTHON:-}" ]]; then
  PYTHON_CMD="${VISUAL_QA_PYTHON}"
elif [[ -x "${ROOT_DIR}/.venv/bin/python" ]]; then
  PYTHON_CMD="${ROOT_DIR}/.venv/bin/python"
else
  PYTHON_CMD="python"
fi

PORT="${VISUAL_QA_PORT:-8012}"
TENANT_SLUG="${TENANT_SLUG:-gilead-school}"
export VISUAL_QA_PORT="$PORT"
export TENANT_ROUTING="${TENANT_ROUTING:-host}"
export TENANT_SLUG="$TENANT_SLUG"
export VISUAL_QA_TENANT_HOST="${VISUAL_QA_TENANT_HOST:-${TENANT_SLUG}.runmycampus.com}"
export TENANT_BASE_URL="${TENANT_BASE_URL:-http://${VISUAL_QA_TENANT_HOST}:${PORT}}"
export TENANT_PREFIX="${TENANT_PREFIX:-/t/${TENANT_SLUG}}"
export VISUAL_QA_TEACHER_USERNAME="${VISUAL_QA_TEACHER_USERNAME:-teacher1}"
export VISUAL_QA_TEACHER_PASSWORD="${VISUAL_QA_TEACHER_PASSWORD:-Sch00l_1234}"
export VISUAL_QA_PARENT_USERNAME="${VISUAL_QA_PARENT_USERNAME:-Parent1}"
export VISUAL_QA_PARENT_PASSWORD="${VISUAL_QA_PARENT_PASSWORD:-Sch00l_1234}"

ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/tenant-portal-lane2}"
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

if [[ "${SKIP_RUNSERVER:-0}" != "1" ]]; then
  echo "tenant-portal-lane2: seed tenant users (${TENANT_SLUG})"
  "$PYTHON_CMD" manage.py seed_render_users 2>/dev/null || true
  "$PYTHON_CMD" manage.py ensure_superuser --no-input --password "${ADMIN_PASSWORD:-Sch00l_1234}" 2>/dev/null || true

  echo "tenant-portal-lane2: starting Django on ${TENANT_BASE_URL}"
  "$PYTHON_CMD" manage.py runserver "0.0.0.0:${PORT}" >"$RUNSERVER_LOG" 2>&1 &
  SERVER_PID=$!

  for _ in $(seq 1 90); do
    if curl -sf -o /dev/null "${TENANT_BASE_URL}/authentication/login/"; then
      break
    fi
    sleep 1
  done
fi

echo "tenant-portal-lane2: Playwright (tenant portal describe)"
npx playwright test tests/e2e/preview-shell-parity.spec.js --grep "tenant portal" --reporter=line

echo "tenant-portal-lane2: TENANT_PORTAL_LANE2_E2E_PASS"
