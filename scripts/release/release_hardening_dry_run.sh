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

TMP_DIR="${PROJECT_ROOT}/.tmp"
mkdir -p "${TMP_DIR}"
TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
UI_CONFIG_PATH="${TMP_DIR}/ui_config_dry_run_${TIMESTAMP}.json"

run_cmd() {
  "$@"
}

echo "[Phase 16] Running release hardening dry-run checks..."
run_cmd "${PYTHON_BIN}" manage.py check
run_cmd "${PYTHON_BIN}" manage.py makemigrations --check --dry-run
run_cmd "${PYTHON_BIN}" manage.py migrate --plan

echo "[Phase 16] Exporting UI config snapshot to ${UI_CONFIG_PATH}"
run_cmd "${PYTHON_BIN}" manage.py export_ui_config --output "${UI_CONFIG_PATH}"

echo "[Phase 16] Printing active theme pointers..."
run_cmd "${PYTHON_BIN}" manage.py shell -c "from apps.siteconfig.models import SiteSettings; s=SiteSettings.get_solo(); print('theme_pack_id=', s.theme_pack_id, 'admin_theme_pack_id=', s.admin_theme_pack_id, 'preview_mode_enabled=', s.preview_mode_enabled)"

echo "[Phase 16] Dry-run complete."
