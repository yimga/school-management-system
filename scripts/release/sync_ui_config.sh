#!/usr/bin/env bash
set -euo pipefail

MODE="${1:-roundtrip}"
PROJECT_ROOT="${PROJECT_ROOT:-}"
PYTHON_PATH="${PYTHON_PATH:-}"
CONFIG_PATH="${CONFIG_PATH:-}"
SKIP_NORMALIZE="${SKIP_NORMALIZE:-0}"

if [[ -z "$PROJECT_ROOT" ]]; then
  SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  PROJECT_ROOT="$(cd "${SCRIPT_DIR}/../.." && pwd)"
fi

if [[ -z "$PYTHON_PATH" ]]; then
  if [[ -x "${PROJECT_ROOT}/.venv/bin/python" ]]; then
    PYTHON_PATH="${PROJECT_ROOT}/.venv/bin/python"
  elif [[ -x "${PROJECT_ROOT}/.venv/Scripts/python.exe" ]]; then
    PYTHON_PATH="${PROJECT_ROOT}/.venv/Scripts/python.exe"
  else
    PYTHON_PATH="python"
  fi
fi

MANAGE_PY="${PROJECT_ROOT}/manage.py"
if [[ ! -f "$MANAGE_PY" ]]; then
  echo "manage.py not found: ${MANAGE_PY}" >&2
  exit 1
fi

if [[ -z "$CONFIG_PATH" ]]; then
  CONFIG_PATH="${PROJECT_ROOT}/fixtures/ui_config.json"
fi

run_manage() {
  "$PYTHON_PATH" "$MANAGE_PY" "$@"
}

case "$MODE" in
  export)
    mkdir -p "$(dirname "$CONFIG_PATH")"
    run_manage export_ui_config --output "$CONFIG_PATH"
    echo "Exported UI config to ${CONFIG_PATH}"
    ;;
  import)
    if [[ ! -f "$CONFIG_PATH" ]]; then
      echo "Config file not found: ${CONFIG_PATH}" >&2
      exit 1
    fi
    run_manage import_ui_config "$CONFIG_PATH"
    if [[ "$SKIP_NORMALIZE" != "1" ]]; then
      run_manage normalize_ui_config
    fi
    echo "Imported UI config from ${CONFIG_PATH}"
    ;;
  normalize)
    run_manage normalize_ui_config
    echo "Normalized UI config."
    ;;
  roundtrip)
    mkdir -p "$(dirname "$CONFIG_PATH")"
    run_manage export_ui_config --output "$CONFIG_PATH"
    run_manage import_ui_config "$CONFIG_PATH"
    if [[ "$SKIP_NORMALIZE" != "1" ]]; then
      run_manage normalize_ui_config
    fi
    echo "Roundtrip export/import complete: ${CONFIG_PATH}"
    ;;
  *)
    echo "Unsupported mode: ${MODE}" >&2
    echo "Usage: sync_ui_config.sh [export|import|normalize|roundtrip]" >&2
    exit 1
    ;;
esac
