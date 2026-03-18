#!/usr/bin/env bash
# Official UX release bar: Playwright (manager + marketing + tenant portals when Postgres),
# then the rest of pre_deploy_gate without re-running Playwright.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$ROOT"

echo "[full_ux_assurance] Node + Playwright chromium"
if ! command -v node >/dev/null 2>&1; then
  echo "Install Node.js for visual QA." >&2
  exit 1
fi
[[ -d node_modules ]] || npm ci
npx playwright install chromium 2>/dev/null || npx playwright install chromium

echo "[full_ux_assurance] Step 1/2 — run_visual_qa.sh (screenshots under artifacts/visual-qa/)"
bash scripts/run_visual_qa.sh

echo "[full_ux_assurance] Step 2/2 — pre_deploy_gate (visual QA skipped; already passed above)"
SKIP_VISUAL_QA=1 bash scripts/pre_deploy_gate.sh

echo "[full_ux_assurance] PASSED — UX bar + deploy gate complete."
