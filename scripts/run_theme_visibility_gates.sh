#!/usr/bin/env bash
# Theme visibility closure bundle (replaces manual gate checklist before deploy).
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

echo "[theme-gates] verify_theme_visibility_platform"
"${PYTHON_CMD}" scripts/verify_theme_visibility_platform.py

echo "[theme-gates] scan_main_content_text_utilities"
"${PYTHON_CMD}" scripts/scan_main_content_text_utilities.py

echo "[theme-gates] audit_template_render_safety"
"${PYTHON_CMD}" scripts/audit_template_render_safety.py

echo "[theme-gates] Django theme matrix tests"
"${PYTHON_CMD}" scripts/run_sqlite_memory_tests.py apps.siteconfig.tests.test_theme_visibility_matrix --verbosity=1

if [[ "${SKIP_THEME_PLAYWRIGHT:-0}" != "1" ]] && [[ -f node_modules/playwright/cli.js ]]; then
  echo "[theme-gates] Manager Playwright (parity + theme visibility)"
  bash scripts/run_manager_surface_parity.sh
else
  echo "[theme-gates] Skipping Playwright (SKIP_THEME_PLAYWRIGHT=1 or npm deps missing)"
fi

echo "OK run_theme_visibility_gates: all automated theme gates passed"
