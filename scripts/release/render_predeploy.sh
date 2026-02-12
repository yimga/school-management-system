#!/usr/bin/env bash
set -euo pipefail

# Render pre-deploy orchestration.
# Keeps production boot deterministic and fail-fast on integration blockers.

PYTHON_BIN="${VENV_PYTHON:-.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python"
fi

run() {
  echo "[predeploy] $*"
  "$@"
}

if [[ "${SKIP_DB_MIGRATIONS:-0}" != "1" ]]; then
  run "${PYTHON_BIN}" manage.py migrate --noinput
fi

run "${PYTHON_BIN}" manage.py seed_admin_dashboard_palettes

if [[ "${APPLY_UI_FIXTURE_ON_DEPLOY:-1}" == "1" && -f "fixtures/ui_config.json" ]]; then
  run "${PYTHON_BIN}" manage.py import_ui_config fixtures/ui_config.json
fi

run "${PYTHON_BIN}" manage.py normalize_ui_config

if [[ "${RUN_INTEGRATION_PREFLIGHT:-1}" == "1" ]]; then
  # Fails with exit code 2 only when a feature is enabled but runtime is not ready.
  run "${PYTHON_BIN}" manage.py integration_preflight
fi

if [[ -n "${ADMIN_PASSWORD:-}" ]]; then
  run "${PYTHON_BIN}" manage.py seed_render_users
else
  echo "[predeploy] ADMIN_PASSWORD not set; skipping seed_render_users."
fi

echo "[predeploy] complete"
