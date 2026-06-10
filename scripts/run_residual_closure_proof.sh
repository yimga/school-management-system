#!/usr/bin/env bash
# Batch 1701 — residual closure proof (tenant isolation, Z-F phases, Playwright phase1/2).
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
TENANT_SLUG="${TENANT_SLUG:-demo-school}"
export VISUAL_QA_PORT="$PORT"
export REDIS_URL=""
export RMC_FORCE_DB_SESSIONS=1
export MANAGER_BASE_URL="${MANAGER_BASE_URL:-http://manager.runmycampus.com:${PORT}}"
export PLAYWRIGHT_TENANT_BASE_URL="${PLAYWRIGHT_TENANT_BASE_URL:-http://127.0.0.1:${PORT}/t/${TENANT_SLUG}}"
export TENANT_E2E_BASE_URL="$PLAYWRIGHT_TENANT_BASE_URL"
export TENANT_E2E_SUBDOMAIN="${TENANT_E2E_SUBDOMAIN:-0}"
export E2E_TENANT_USER="${E2E_TENANT_USER:-demo.admin}"
export E2E_TENANT_PASSWORD="${E2E_TENANT_PASSWORD:-Test1234}"
export DEFAULT_TENANT_ADMIN_PASSWORD="${DEFAULT_TENANT_ADMIN_PASSWORD:-Test1234}"

ARTIFACT_DIR="${ARTIFACT_DIR:-artifacts/residual-closure-1701}"
mkdir -p "$ARTIFACT_DIR"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"
PROOF_LOG="${ARTIFACT_DIR}/proof.log"

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

exec > >(tee -a "$PROOF_LOG") 2>&1

echo "=== residual-closure-1701: migrate + seed demo tenant ==="
"$PYTHON_CMD" manage.py migrate --noinput
"$PYTHON_CMD" manage.py ensure_developer_sandbox_tenant --school-slug="$TENANT_SLUG" --password="$E2E_TENANT_PASSWORD"
"$PYTHON_CMD" manage.py seed_demo_tenant_users --school-slug="$TENANT_SLUG" --password="$E2E_TENANT_PASSWORD"
"$PYTHON_CMD" manage.py seed_render_users 2>/dev/null || true
"$PYTHON_CMD" manage.py ensure_superuser --no-input --password "$E2E_TENANT_PASSWORD" 2>/dev/null || true

echo "=== residual-closure-1701: repo verifiers ==="
"$PYTHON_CMD" scripts/scan_tenant_queryset_safety.py --compare
"$PYTHON_CMD" scripts/verify_zero_friction_phases_0_8.py
"$PYTHON_CMD" scripts/verify_zero_friction_journeys.py

echo "=== residual-closure-1701: Django runserver on :${PORT} ==="
nohup env \
  SECURE_SSL_REDIRECT=0 \
  DEBUG=1 \
  CSRF_COOKIE_SECURE=0 \
  SESSION_COOKIE_SECURE=0 \
  "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
SERVER_PID=$!

for _ in $(seq 1 90); do
  if curl -sf -o /dev/null "http://127.0.0.1:${PORT}/t/${TENANT_SLUG}/authentication/login/"; then
    break
  fi
  sleep 2
done

echo "=== residual-closure-1701: Playwright phase1 + phase2 ==="
npm run test:e2e:phase1-architecture
npm run test:e2e:phase2-portal

echo "RESIDUAL_CLOSURE_PLAYWRIGHT_PASS"
