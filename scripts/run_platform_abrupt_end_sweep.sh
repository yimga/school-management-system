#!/usr/bin/env bash
# Full abrupt-end sweep: regenerate route JSON, optional health wait, Playwright.
#
# Prerequisites:
#   - Django listening on VISUAL_QA_PORT (default 8012)
#   - Host mapping: manager.runmycampus.com -> 127.0.0.1 (PLAYWRIGHT_HOST_RULES in Node)
#   - Optional: artifacts/manager-playwright-auth.json for manager login
#
# Usage:
#   export VISUAL_QA_PORT=8012
#   export SWEEP_TIER=operator+admin    # default below
#   bash scripts/run_platform_abrupt_end_sweep.sh
#
# Env:
#   SWEEP_TIER          operator | operator+admin | all (default: operator+admin)
#   SWEEP_SKIP_HEALTH   set to 1 to skip waiting for /ready/
#   SWEEP_HEALTH_SECS   max seconds to wait for server (default 120)
#   SWEEP_GOTO_RETRIES  passed to Node (default 3)
#   TENANT_SWEEP_MAX    cap tenant routes (default 200)

set -euo pipefail
# Prevent Git Bash from rewriting `/configuration/` and `/t/...` in env vars.
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

HOST="${VISUAL_QA_MANAGER_HOST:-manager.runmycampus.com}"
PORT="${VISUAL_QA_PORT:-8012}"
BASE_URL="${MANAGER_BASE_URL:-http://${HOST}:${PORT}}"
TIER="${SWEEP_TIER:-operator+admin}"
HEALTH_MAX="${SWEEP_HEALTH_SECS:-120}"

python scripts/generate_control_plane_sweep_routes.py --write
python scripts/generate_portal_tenant_sweep_routes.py --write

if [[ "${SWEEP_SKIP_HEALTH:-0}" != "1" ]]; then
  echo "Waiting for ${BASE_URL}/ready/ (max ${HEALTH_MAX}s)..."
  for ((i = 0; i < HEALTH_MAX; i++)); do
    if curl -fsS -m 3 -H "Host: ${HOST}" "${BASE_URL}/ready/" >/dev/null 2>&1; then
      echo "Server ready."
      break
    fi
    if ((i == HEALTH_MAX - 1)); then
      echo "WARN: health check did not succeed; sweep may fail on connection errors." >&2
    fi
    sleep 1
  done
fi

export SWEEP_TIER="$TIER"
export SWEEP_GOTO_RETRIES="${SWEEP_GOTO_RETRIES:-3}"
node scripts/verify_platform_abrupt_end_sweep.mjs
