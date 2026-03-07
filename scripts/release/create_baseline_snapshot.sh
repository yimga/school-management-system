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

timestamp="$(date +"%Y%m%d_%H%M%S")"
backup_root="${PROJECT_ROOT}/backups/phase0"
db_backup_dir="${backup_root}/db"
config_backup_dir="${backup_root}/ui_config"

mkdir -p "${db_backup_dir}" "${config_backup_dir}"

db_candidate=""
if [[ -f "${PROJECT_ROOT}/db_working.sqlite3" ]]; then
  db_candidate="${PROJECT_ROOT}/db_working.sqlite3"
elif [[ -f "${PROJECT_ROOT}/db.sqlite3" ]]; then
  db_candidate="${PROJECT_ROOT}/db.sqlite3"
fi

if [[ -n "${db_candidate}" ]]; then
  db_name="$(basename "${db_candidate}")"
  db_target="${db_backup_dir}/${db_name%.sqlite3}_${timestamp}.sqlite3"
  cp "${db_candidate}" "${db_target}"
  echo "DB snapshot created: ${db_target}"
else
  echo "DB snapshot skipped: no local sqlite database found"
fi

config_target="${config_backup_dir}/ui_config_${timestamp}.json"
"${PYTHON_BIN}" manage.py export_ui_config --output "${config_target}"
echo "UI config snapshot created: ${config_target}"

meta_file="${backup_root}/snapshot_meta_${timestamp}.txt"
{
  echo "timestamp=${timestamp}"
  echo "project_root=${PROJECT_ROOT}"
  echo "python_bin=${PYTHON_BIN}"
  echo "git_commit=$(git rev-parse HEAD 2>/dev/null || echo unknown)"
  echo "git_branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"
  echo "git_dirty=$(git status --porcelain 2>/dev/null | wc -l | tr -d ' ')"
} > "${meta_file}"

echo "Phase 0 baseline snapshot complete."
