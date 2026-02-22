#!/usr/bin/env bash
# Phase I: Run DB health check after migrations and before starting Gunicorn.
# Usage: from render_predeploy.sh or Docker entrypoint after migrate/migrate_schemas.
set -euo pipefail
PYTHON_BIN="${VENV_PYTHON:-.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python"
fi
echo "[health-check] Running DB health check..."
"${PYTHON_BIN}" manage.py db_health_check
echo "[health-check] OK"
