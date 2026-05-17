#!/usr/bin/env bash
# Marketing visual-regression snapshots (Playwright toHaveScreenshot).
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
PUBLIC_HOST="${VISUAL_QA_PUBLIC_HOST:-runmycampus.com}"
ARTIFACT_DIR="${VISUAL_QA_ARTIFACT_DIR:-artifacts/marketing-snapshots}"
RUNSERVER_LOG="${ARTIFACT_DIR}/runserver.log"

mkdir -p "$ARTIFACT_DIR"

if [[ ! -f "node_modules/playwright/cli.js" ]]; then
  echo "run_marketing_snapshots: run npm ci first." >&2
  exit 1
fi

SERVER_PID=""
cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

if curl -s -o /dev/null -w '%{http_code}' -H "Host: ${PUBLIC_HOST}" "http://127.0.0.1:${PORT}/" | grep -q '^200$'; then
  echo "[run_marketing_snapshots] Reusing server on port ${PORT}"
else
  nohup env SECURE_SSL_REDIRECT=0 DEBUG=1 CSRF_TRUSTED_ORIGINS="http://127.0.0.1:${PORT},http://${PUBLIC_HOST}:${PORT}" \
    "$PYTHON_CMD" manage.py runserver "127.0.0.1:${PORT}" --noreload >"$RUNSERVER_LOG" 2>&1 &
  SERVER_PID="$!"
  for _ in $(seq 1 45); do
    code="$(curl -s -o /dev/null -w '%{http_code}' -H "Host: ${PUBLIC_HOST}" "http://127.0.0.1:${PORT}/" || true)"
    [[ "$code" == "200" ]] && break
    sleep 2
  done
  if [[ "${code:-}" != "200" ]]; then
    echo "run_marketing_snapshots: server not ready (HTTP ${code:-none})." >&2
    tail -n 40 "$RUNSERVER_LOG" >&2 || true
    exit 1
  fi
fi

export MARKETING_BASE_URL="http://${PUBLIC_HOST}:${PORT}"
export PLAYWRIGHT_HOST_RULES="MAP ${PUBLIC_HOST} 127.0.0.1"

PW_ARGS=(test tests/e2e/marketing-snapshots.spec.js --reporter=line)
if [[ "${UPDATE_SNAPSHOTS:-}" == "1" ]]; then
  PW_ARGS+=(--update-snapshots)
fi

node node_modules/playwright/cli.js "${PW_ARGS[@]}"
