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

CONFIG_PATH="${1:-${PROJECT_ROOT}/fixtures/ui_config.json}"

"${PYTHON_BIN}" manage.py check_ui_parity --input-file "${CONFIG_PATH}" --strict
echo "UI parity check passed against ${CONFIG_PATH}"
