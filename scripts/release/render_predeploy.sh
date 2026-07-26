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

# Fail fast when Django admin approval HTML parity lock drifts (visible chip /
# cache-bust / SW / grid). Catches the class of "deploy looked the same" bugs
# where CSS-only or un-pushed layout waves never reach production markers.
run "${PYTHON_BIN}" scripts/verify_django_admin_preview_parity.py

# Fail fast when shell includes reference a template missing from the checkout.
WFP_STRIP="templates/components/rmc_workflow_progress_strip.html"
if [[ ! -f "${WFP_STRIP}" ]]; then
  echo "[predeploy] FATAL: missing ${WFP_STRIP} (required by portal_base + manager topbar / deploy readiness gate)"
  exit 1
fi

run "${PYTHON_BIN}" scripts/verify_render_deploy_readiness.py

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
    # Legacy people_* tables in public schema never get migrate_schemas --tenant; heal drift.
    run "${PYTHON_BIN}" manage.py repair_teacherprofile_updated_at
    run "${PYTHON_BIN}" manage.py ensure_all_user_identities --active-only
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

# Marketplace permission-scope catalog: keeps the DB-side scope rows aligned
# with the code-level SCOPE_CATALOG on every deploy. update_or_create per
# scope — idempotent, safe to re-run.
run "${PYTHON_BIN}" manage.py seed_marketplace_scopes

# Migration Cloud connector registry: keeps the DB-side MigrationConnectorProfile
# rows aligned with the code-level PROFILES catalog on every deploy. update_or_create
# per profile — idempotent, safe to re-run. Without this the tenant "Connect source
# platform" dropdown renders empty (the profile table is otherwise never seeded).
# The 0035 data migration also seeds it, so this is the ongoing re-sync as the
# catalog grows.
run "${PYTHON_BIN}" manage.py seed_migration_connector_profiles

# Subscription plan / add-on / promotion catalog. update_or_create per row —
# idempotent, safe to re-run. This is also the ONLY producer of a plan with
# is_default=True (free-starter), which Plan.get_default_plan() reads to bind a
# brand-new tenant's School.plan. Without it get_default_plan() returns None, the
# default-plan binding in ensure_subscription_for_school silently no-ops, and every
# tenant lands plan-less — which is default-OPEN (is_feature_enabled falls through
# to the base manifest when school.plan is None), so no entitlement or usage cap
# applies. Migration 0200 only *marks* a pre-existing Plan, so on a fresh DB it runs
# before any Plan row exists and marks nothing. Plan.save() keeps the single-default
# invariant, so re-seeding cannot trip the plan_unique_default constraint.
run "${PYTHON_BIN}" manage.py seed_subscription_catalog

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

# Opt-in tenant test-account seeding (idempotent). When SEED_TENANT_TEST_ACCOUNTS_SLUG
# is set (e.g. "gilead-tech"), attach the owner + create teacher1/parent1 (password
# Test1234) WITH SchoolMembership on that tenant — the linkage seed_render_users'
# create_teacher_parent_accounts does NOT establish. Owner is attached by email
# (created with an unusable password if absent, set via the setup email link).
# Non-fatal: a bad slug/owner value logs and is skipped, never blocking the deploy.
if [[ -n "${SEED_TENANT_TEST_ACCOUNTS_SLUG:-}" ]]; then
  SEED_TT_ARGS=(seed_tenant_test_accounts --slug "${SEED_TENANT_TEST_ACCOUNTS_SLUG}" --create-owner-if-missing)
  if [[ -n "${SEED_TENANT_TEST_OWNER_EMAIL:-}" ]]; then
    SEED_TT_ARGS+=(--owner-email "${SEED_TENANT_TEST_OWNER_EMAIL}")
    if [[ "${SEED_TENANT_TEST_SEND_OWNER_EMAIL:-1}" == "1" ]]; then
      SEED_TT_ARGS+=(--send-owner-email)
    fi
  fi
  if [[ -n "${SEED_TENANT_TEST_PASSWORD:-}" ]]; then
    SEED_TT_ARGS+=(--password "${SEED_TENANT_TEST_PASSWORD}")
  fi
  run "${PYTHON_BIN}" manage.py "${SEED_TT_ARGS[@]}" \
    || echo "[predeploy] seed_tenant_test_accounts skipped/failed (non-fatal); check SEED_TENANT_TEST_* env"
fi

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

# Starter Knowledge Base articles (per-tenant content). Opt-in (default 0) so
# steady-state deploys stay fast. Idempotent (get_or_create on slug); content is
# country-neutral. Seeds every tenant schema; one tenant's failure is logged and
# skipped, never aborting the deploy. Flip RUN_SEED_KB_ARTICLES=1 for a one-time
# backfill when you want tenant KBs populated.
if [[ "${RUN_SEED_KB_ARTICLES:-0}" == "1" ]]; then
  if [[ "${TENANT_MODE}" == "1" ]]; then
    run "${PYTHON_BIN}" manage.py seed_kb_articles --all-tenants
  else
    run "${PYTHON_BIN}" manage.py seed_kb_articles
  fi
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

# Worldwide weather city catalog (~30k rows). Idempotent; first run can take minutes.
# Also included when bootstrap_platform_catalog --all runs (seed_global_data --with-weather-locations).
# Default OFF so predeploy stays fast; flip RUN_SEED_GLOBAL_WEATHER_LOCATIONS=1 after siteconfig 0180/0181 migrate.
if [[ "${RUN_SEED_GLOBAL_WEATHER_LOCATIONS:-0}" == "1" ]]; then
  run "${PYTHON_BIN}" manage.py seed_global_weather_locations
fi

# World Footprint WebGL bundle (gitignored under static/js/dist/) — rebuild if build.sh skipped it.
GLOBE_SRC="static/js/dist/world-globe.mount.js"
globe_source_ok() {
  [[ -f "${GLOBE_SRC}" ]] && [[ "$(wc -c < "${GLOBE_SRC}")" -ge 500000 ]]
}
if ! globe_source_ok; then
  echo "[predeploy] world globe bundle missing or too small — rebuilding"
  if ! command -v npm >/dev/null 2>&1; then
    echo "[predeploy] FATAL: npm is required to build static/js/dist/world-globe.mount.js"
    exit 1
  fi
  npm ci --no-audit --no-fund 2>/dev/null || npm install --no-audit --no-fund
  run "${PYTHON_BIN}" scripts/purge_retired_globe_vendor_chunks.py
  npm run build:world-globe
  run "${PYTHON_BIN}" scripts/generate_globe_earth_night_texture.py
  run "${PYTHON_BIN}" scripts/verify_world_globe_staticfiles_deploy.py --source
fi

# Collect static files (required for WhiteNoise/serving)
run "${PYTHON_BIN}" manage.py collectstatic --noinput --clear
run "${PYTHON_BIN}" scripts/verify_world_globe_staticfiles_deploy.py --staticfiles

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
