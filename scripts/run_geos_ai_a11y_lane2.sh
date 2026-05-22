#!/usr/bin/env bash
# Lane 2: Playwright axe on help + AI Center (requires live Django + GEOS_A11Y_E2E=1).
set -euo pipefail
cd "$(dirname "$0")/.."
export GEOS_A11Y_E2E=1
export VISUAL_QA_PORT="${VISUAL_QA_PORT:-8014}"
export VISUAL_QA_BASE_URL="${VISUAL_QA_BASE_URL:-http://127.0.0.1:${VISUAL_QA_PORT}}"
echo "GEOS AI a11y sweep against ${VISUAL_QA_BASE_URL}"
npm run test:e2e:help-ai-center-a11y
