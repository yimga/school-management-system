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
  TENANT_MODE="$("${PYTHON_BIN}" - <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.conf import settings
print("1" if getattr(settings, "USE_DJANGO_TENANTS", False) else "0")
PY
)"
  if [[ "${TENANT_MODE}" == "1" ]]; then
    run "${PYTHON_BIN}" manage.py migrate_schemas --shared --noinput
    run "${PYTHON_BIN}" manage.py migrate_schemas --tenant --noinput
  else
    run "${PYTHON_BIN}" manage.py migrate --noinput
  fi
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

# Phase I: DB health check before traffic (so orchestrator only routes when DB is ready)
if [[ -f "scripts/release/run_health_check.sh" ]]; then
  bash scripts/release/run_health_check.sh
fi

echo "[predeploy] complete"
