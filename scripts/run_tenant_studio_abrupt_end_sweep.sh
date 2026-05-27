#!/usr/bin/env bash
# Playwright abrupt-end sweep for tenant School Studio routes only.
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

export SWEEP_INCLUDE_TENANT=1
export SWEEP_TIER=tenant
export SWEEP_TENANT_PATHS="/t/demo-school/school/studio/,/school/studio/,/school/studio/lifecycle/,/school/studio/offboarding/,/school/studio/provisioning/"
export TENANT_SWEEP_MAX="${TENANT_SWEEP_MAX:-200}"

PORT="${VISUAL_QA_PORT:-8012}"
HOST="${VISUAL_QA_TENANT_HOST:-demo-school.runmycampus.com}"
export TENANT_BASE_URL="${TENANT_BASE_URL:-http://${HOST}:${PORT}}"
export VISUAL_QA_PORT="${PORT}"
HEALTH_MAX="${SWEEP_HEALTH_SECS:-300}"
ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/tenant-studio-sweep}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"
START_SERVER="${START_SERVER:-1}"

mkdir -p "$ARTIFACT_DIR"

TENANT_SLUG="${TENANT_SWEEP_SLUG:-demo-school}"
export TENANT_SWEEP_SLUG="${TENANT_SLUG}"

"${PYTHON_CMD}" manage.py migrate --noinput
"${PYTHON_CMD}" manage.py ensure_demo_environment --school-slug="${TENANT_SLUG}" 2>/dev/null || true
"${PYTHON_CMD}" manage.py seed_render_users 2>/dev/null || true
"${PYTHON_CMD}" scripts/generate_portal_tenant_sweep_routes.py --write

SERVER_PID=""
if [[ "${START_SERVER}" == "1" ]]; then
  if curl -fsS -m 2 -H "Host: ${HOST}" "${TENANT_BASE_URL}/ready/" >/dev/null 2>&1; then
    echo "Using existing server at ${TENANT_BASE_URL}"
  else
    echo "Starting Django on :${PORT} (log: ${RUNSERVER_LOG})..."
    "${PYTHON_CMD}" manage.py runserver "0.0.0.0:${PORT}" --noreload >>"${RUNSERVER_LOG}" 2>&1 &
    SERVER_PID=$!
    trap '[[ -n "${SERVER_PID}" ]] && kill "${SERVER_PID}" 2>/dev/null || true' EXIT
  fi
fi

if [[ "${SWEEP_SKIP_HEALTH:-0}" != "1" ]]; then
  echo "Waiting for ${TENANT_BASE_URL}/ready/ (max ${HEALTH_MAX}s)..."
  for ((i = 0; i < HEALTH_MAX; i++)); do
    if curl -fsS -m 3 -H "Host: ${HOST}" "${TENANT_BASE_URL}/ready/" >/dev/null 2>&1; then
      echo "Tenant server ready."
      break
    fi
    if ((i == HEALTH_MAX - 1)); then
      echo "ERROR: server not ready; cannot sweep." >&2
      exit 1
    fi
    sleep 1
  done
fi

node scripts/verify_platform_abrupt_end_sweep.mjs
echo "Tenant School Studio abrupt-end sweep: OK"
