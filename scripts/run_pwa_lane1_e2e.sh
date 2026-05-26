#!/usr/bin/env bash
# Lane 1 PWA offline Playwright sweep (in-repo). See docs/PWA_LANE2_OPERATOR_RUNBOOK_2026_05_26.md
set -euo pipefail
cd "$(dirname "$0")/.."
export RMC_PLAYWRIGHT_HOST="${RMC_PLAYWRIGHT_HOST:-http://127.0.0.1:8000}"
npx playwright test tests/e2e/pwa-offline.spec.js "$@"
