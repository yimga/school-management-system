#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
cd "${PROJECT_ROOT}"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "${PYTHON_BIN}" ]]; then
  if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/.venv/bin/python"
  elif [[ -x "${PROJECT_ROOT}/.venv/Scripts/python.exe" ]]; then
    PYTHON_BIN="${PROJECT_ROOT}/.venv/Scripts/python.exe"
  else
    PYTHON_BIN="python"
  fi
fi

run_cmd() {
  "$@"
}

echo "[Phase 15] Running Django system checks..."
run_cmd "${PYTHON_BIN}" manage.py check

echo "[Phase 15] Verifying migrations are in sync..."
run_cmd "${PYTHON_BIN}" manage.py makemigrations --check --dry-run

test_modules=(
  "apps.portal.tests.test_generate_kb_odt_command"
  "apps.siteconfig.tests.test_theme_studio"
  "apps.siteconfig.tests.test_preview"
  "apps.siteconfig.tests.test_reportcard_builder"
  "apps.siteconfig.tests.test_redirect_safety"
  "apps.siteconfig.tests.test_admin_ui_smoke"
  "apps.requests.tests.test_views_security"
  "apps.accounts.tests.test_mfa_redirect_safety"
  "apps.reports.tests.test_publish_term"
)

echo "[Phase 15] Running targeted regression suite..."
run_cmd "${PYTHON_BIN}" manage.py test "${test_modules[@]}" --verbosity 1

echo "[Phase 15] Final gate passed."
