#!/usr/bin/env bash
# E2E: tenant School Studio Playwright spec + optional abrupt-end sweep.
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
export VISUAL_QA_PORT="${PORT}"
export TENANT_BASE_URL="${TENANT_BASE_URL:-http://demo-school.runmycampus.com:${PORT}}"
export USE_TENANT_SUBDOMAIN="${USE_TENANT_SUBDOMAIN:-1}"
ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/tenant-studio-e2e}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"
START_SERVER="${START_SERVER:-1}"

mkdir -p "$ARTIFACT_DIR"
"${PYTHON_CMD}" manage.py migrate --noinput
"${PYTHON_CMD}" scripts/generate_portal_tenant_sweep_routes.py --write

if [[ "${START_SERVER}" == "1" ]]; then
  if ! curl -fsS -m 3 -H "Host: demo-school.runmycampus.com" "${TENANT_BASE_URL}/ready/" >/dev/null 2>&1; then
    echo "Starting Django :${PORT} (noreload)…"
    "${PYTHON_CMD}" manage.py runserver "0.0.0.0:${PORT}" --noreload >>"${RUNSERVER_LOG}" 2>&1 &
    SERVER_PID=$!
    trap 'kill "${SERVER_PID}" 2>/dev/null || true' EXIT
    for ((i = 0; i < 300; i++)); do
      if curl -fsS -m 3 -H "Host: demo-school.runmycampus.com" "${TENANT_BASE_URL}/ready/" >/dev/null 2>&1; then
        break
      fi
      sleep 1
    done
  fi
fi

npx playwright test tests/e2e/tenant-school-studio.spec.js

if [[ "${RUN_ABRUPT_SWEEP:-1}" == "1" ]]; then
  START_SERVER=0 SWEEP_SKIP_HEALTH=1 bash scripts/run_tenant_studio_abrupt_end_sweep.sh
fi

echo "Tenant School Studio E2E: OK"
