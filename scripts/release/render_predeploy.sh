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

# Fail fast when migration files are gitignored or not committed (e.g. *Conflict*.py rule).
run "${PYTHON_BIN}" scripts/verify_migration_files_tracked.py

# Fail fast when a new app has migrations but is missing from SHARED_APPS/TENANT_APPS
# (migrate_schemas would skip it on Render).
run "${PYTHON_BIN}" scripts/verify_tenant_schema_app_registration.py

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

  # v3.15 — post-migrate verification gate. Walks every app's migration graph
  # and confirms every node is applied. Also detects model-vs-migrations drift
  # (the "automation has changes" warning from older deploys). Warning-only by
  # default so a benign cosmetic drift doesn't block deploys; flip
  # STRICT_MIGRATION_VERIFY=1 to make it fail-loud.
  if [[ "${STRICT_MIGRATION_VERIFY:-0}" == "1" ]]; then
    if [[ "${TENANT_MODE}" == "1" ]]; then
      run "${PYTHON_BIN}" manage.py verify_all_migrations_applied --strict --include-tenant
    else
      run "${PYTHON_BIN}" manage.py verify_all_migrations_applied --strict
    fi
  else
    if [[ "${TENANT_MODE}" == "1" ]]; then
      run "${PYTHON_BIN}" manage.py verify_all_migrations_applied --include-tenant || true
    else
      run "${PYTHON_BIN}" manage.py verify_all_migrations_applied || true
    fi
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

# pgvector: post-5k-scale embedding store. Migrates JSON embeddings into a
# pgvector column + tuned IVFFLAT index, then verifies the planner uses it.
# Both commands refuse on non-Postgres vendors and are idempotent — safe to
# re-run every deploy. One-time DB superuser step (`CREATE EXTENSION vector;`)
# is handled by the migrate command via `CREATE EXTENSION IF NOT EXISTS vector;`,
# which requires the DB role to have CREATE privilege on the database.
# Set RUN_PGVECTOR_MIGRATE=0 to skip (e.g. tenants below the 5k milestone or
# environments without the vector extension available).
# Monthly rebuild cadence (`rebuild_pgvector_index --vacuum`) is run from
# Celery beat, NOT here — predeploy must stay fast.
if [[ "${RUN_PGVECTOR_MIGRATE:-1}" == "1" ]]; then
  DB_VENDOR="$("${PYTHON_BIN}" - <<'PY'
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
django.setup()
from django.db import connection
print(connection.vendor)
PY
)"
  if [[ "${DB_VENDOR}" == "postgresql" ]]; then
    run "${PYTHON_BIN}" manage.py migrate_embeddings_to_pgvector --write-env-flag
    run "${PYTHON_BIN}" manage.py verify_pgvector_index --strict
  else
    echo "[predeploy] skipping pgvector (vendor=${DB_VENDOR}, requires postgresql)"
  fi
fi

if [[ "${RUN_INTEGRATION_PREFLIGHT:-1}" == "1" ]]; then
  # Fails with exit code 2 only when a feature is enabled but runtime is not ready.
  run "${PYTHON_BIN}" manage.py integration_preflight
fi

# Data residency readiness preflight. Opt-in (default 0) because most
# deploys don't yet have region replicas provisioned. Operators flip this
# to 1 when they're ready to enforce — the next deploy will fail-loud if
# any tenant's data_region is unaligned or its region replica is missing
# from DATABASES. Pair with DATA_RESIDENCY_ENFORCE=1 only AFTER this gate
# is clean — otherwise enforcement raises CrossRegionWriteError mid-request.
if [[ "${RUN_VERIFY_RESIDENCY_READINESS:-0}" == "1" ]]; then
  run "${PYTHON_BIN}" manage.py verify_residency_readiness --quiet
fi

# Always run seed_render_users: ensures super-admin admin/admin. Tenant demo users (teacher1, Parent1, principal1) are created only when ADMIN_PASSWORD is set.
run "${PYTHON_BIN}" manage.py seed_render_users

# AI/ML registry bootstrap. Idempotent: registers the legacy heuristic baseline
# as the PRODUCTION AtRiskModelArtifact if none is registered yet. Without this,
# fresh DBs fall through to the env-var-pointed artifact (or the heuristic
# fallback), and `verify_ai_ml_readiness` reports `production` as failing.
# Skipped automatically when the registry already has a PRODUCTION row.
# v3.14: --operator-username is now optional — the cmd auto-resolves to the
# first superuser (admin), and missing/no artifact paths are graceful skips
# instead of fatal CommandErrors. Predeploy can invoke this without args.
if [[ "${RUN_BOOTSTRAP_AT_RISK_REGISTRY:-1}" == "1" ]]; then
  run "${PYTHON_BIN}" manage.py bootstrap_at_risk_registry
fi

# Platform-wide public-schema seeding. Idempotent — every step routes through
# update_or_create / get_or_create so re-runs are safe. The --skip-tenants flag
# prevents demo data from being created in real tenant schemas; per-tenant demo
# seeding is operator-driven via SEED_DEMO=1 (handled separately below).
# Set RUN_PLATFORM_SEED=0 to opt out of the orchestrator (default ON because
# the user asked for "platform-wide seeding, no exception").
if [[ "${RUN_PLATFORM_SEED:-1}" == "1" ]]; then
  run "${PYTHON_BIN}" manage.py seed_platform_complete --skip-tenants --continue-on-error
fi

# Risk-digest recipients. Opt-in (default 0) because it discovers ADMIN/
# PRINCIPAL/PROPRIETOR users and creates disabled rows; on a fresh deploy
# those users may not exist yet. Flip RUN_SEED_DIGEST_RECIPIENTS=1 once
# the admin pool is provisioned. Idempotent — safe to re-run.
if [[ "${RUN_SEED_DIGEST_RECIPIENTS:-0}" == "1" ]]; then
  run "${PYTHON_BIN}" manage.py seed_default_digest_recipients
fi

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
