#!/usr/bin/env bash
set -euo pipefail

# Render pre-deploy orchestration.
# IMPORTANT: With USE_DJANGO_TENANTS=1 you must use THIS script for pre-deploy,
# not "python manage.py migrate". Plain migrate breaks tenant schemas (no schema selected).
# In Render Dashboard: Pre-Deploy Command = ./scripts/release/render_predeploy.sh

PYTHON_BIN="${VENV_PYTHON:-.venv/bin/python}"
if [[ ! -x "${PYTHON_BIN}" ]]; then
  PYTHON_BIN="python"
fi

run() {
  echo "[predeploy] $*"
  "$@"
}

# Detect tenant mode once (used for migrate block and for re-migrate before import_ui_config).
TENANT_MODE="$("${PYTHON_BIN}" - <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.conf import settings
print("1" if getattr(settings, "USE_DJANGO_TENANTS", False) else "0")
PY
)"
if [[ "${SKIP_DB_MIGRATIONS:-0}" != "1" ]]; then
  if [[ "${TENANT_MODE}" == "1" ]]; then
    run "${PYTHON_BIN}" manage.py migrate_schemas --shared --noinput
    # Create any missing tenant schemas (Clients created in migrations may not have schema yet)
    run "${PYTHON_BIN}" manage.py ensure_tenant_schemas
    run "${PYTHON_BIN}" manage.py migrate_schemas --tenant --noinput
    # Ensure every active school has Client + Domain (canonical base domain); idempotent.
    run "${PYTHON_BIN}" manage.py migrate_schools_to_tenants
    # New schools may get schemas here; apply tenant migrations again before later steps.
    run "${PYTHON_BIN}" manage.py migrate_schemas --tenant --noinput
  else
    run "${PYTHON_BIN}" manage.py migrate --noinput
  fi
fi

# (TENANT_MODE remains set for use below when re-running tenant migrations before import_ui_config)

if [[ "${RUN_BACKFILL_SCHOOLDOMAIN:-1}" == "1" ]]; then
  run "${PYTHON_BIN}" manage.py backfill_schooldomain
fi

if [[ "${RUN_STARTUP_SCHEMA_CHECK:-1}" == "1" ]]; then
  run "${PYTHON_BIN}" manage.py check_tenant_runtime
fi

run "${PYTHON_BIN}" manage.py seed_admin_dashboard_palettes

if [[ "${APPLY_UI_FIXTURE_ON_DEPLOY:-1}" == "1" && -f "fixtures/ui_config.json" ]]; then
  # Ensure all tenant schemas have latest migrations (e.g. finance.ComplianceProfile.vat_rate)
  # before import_ui_config touches tenant models.
  if [[ "${TENANT_MODE}" == "1" ]]; then
    run "${PYTHON_BIN}" manage.py migrate_schemas --tenant --noinput
  fi
  run "${PYTHON_BIN}" manage.py import_ui_config fixtures/ui_config.json
fi

run "${PYTHON_BIN}" manage.py normalize_ui_config

if [[ "${RUN_INTEGRATION_PREFLIGHT:-1}" == "1" ]]; then
  # Fails with exit code 2 only when a feature is enabled but runtime is not ready.
  run "${PYTHON_BIN}" manage.py integration_preflight
fi

# Always run seed_render_users: ensures super-admin admin/admin. Tenant demo users (teacher1, Parent1, principal1) are created only when ADMIN_PASSWORD is set.
run "${PYTHON_BIN}" manage.py seed_render_users

if [[ "${SEED_DEMO:-0}" == "1" ]]; then
  run "${PYTHON_BIN}" manage.py seed_demo --reset
fi

# Optional: bootstrap platform catalogs so Manager surfaces are populated (idempotent).
# Default when RUN_BOOTSTRAP_PLATFORM_CATALOG=1: full bootstrap (--all). Set RUN_MINIMAL_BOOTSTRAP=1 for blueprint+marketplace only.
if [[ "${RUN_BOOTSTRAP_PLATFORM_CATALOG:-0}" == "1" ]]; then
  if [[ "${RUN_MINIMAL_BOOTSTRAP:-0}" == "1" ]]; then
    run "${PYTHON_BIN}" manage.py bootstrap_platform_catalog
  else
    run "${PYTHON_BIN}" manage.py bootstrap_platform_catalog --all
  fi
fi

# Collect static files (required for WhiteNoise/serving)
run "${PYTHON_BIN}" manage.py collectstatic --noinput --clear

# Phase I: DB health check before traffic (so orchestrator only routes when DB is ready)
if [[ -f "scripts/release/run_health_check.sh" ]]; then
  bash scripts/release/run_health_check.sh
fi


# Optional Collabora readiness ping during predeploy (non-blocking unless enabled).
if [[ "${RUN_COLLABORA_READINESS_CHECK:-0}" == "1" ]]; then
  if [[ -n "${COLLABORA_BASE_URL:-}" ]]; then
    run "${PYTHON_BIN}" scripts/verify_collabora_wopi_smoke.py \
      --app-base "${APP_BASE_URL:-}" \
      --collabora-base "${COLLABORA_BASE_URL}"
  fi
fi

echo "[predeploy] complete"
