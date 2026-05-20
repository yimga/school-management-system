#!/usr/bin/env bash
# Full platform /admin/ proof: Django render crawl (all changelists) + Playwright abrupt-end.
#
# Prerequisites (Playwright leg):
#   - Django on VISUAL_QA_PORT (default 8012)
#   - manager.runmycampus.com -> 127.0.0.1
#   - Optional: artifacts/manager-playwright-auth.json
#
# Usage:
#   bash scripts/run_admin_full_proof_bundle.sh
#   ADMIN_RENDER_ONLY=1 bash scripts/run_admin_full_proof_bundle.sh   # skip Playwright
#   PLAYWRIGHT_ONLY=1 bash scripts/run_admin_full_proof_bundle.sh     # skip Django crawl
#
set -euo pipefail
export MSYS_NO_PATHCONV=1
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "== Admin full proof bundle =="

python scripts/generate_control_plane_sweep_routes.py --write

if [[ "${PLAYWRIGHT_ONLY:-0}" != "1" ]]; then
  echo "== Django ADMIN_RENDER_FULL crawl =="
  ADMIN_RENDER_FULL=1 python scripts/verify_admin_changelist_render_contract.py --write
fi

if [[ "${ADMIN_RENDER_ONLY:-0}" != "1" ]]; then
  echo "== Playwright admin abrupt-end sweep =="
  export SWEEP_TIER=admin_changelist
  export SWEEP_PATHS=/admin/
  export SWEEP_INCLUDE_TENANT=0
  export SWEEP_SKIP_HEALTH="${SWEEP_SKIP_HEALTH:-0}"
  export SWEEP_HEALTH_SECS="${SWEEP_HEALTH_SECS:-120}"
  bash scripts/run_admin_abrupt_end_sweep.sh
fi

echo "== Admin full proof bundle: OK =="
