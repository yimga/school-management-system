#!/usr/bin/env bash
# Beyond-reach regression tests (same set as pre_deploy_gate BR slice).
# Uses a dedicated SQLite file to avoid WinError 32 on shared default.sqlite3.
# BR-13: manual only — run docs/PREMIUM_UX_MANUAL_PASS_BR13.md per release.
set -euo pipefail
_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DJANGO_TEST_DB_FILE="${DJANGO_TEST_DB_FILE:-$_ROOT/.django_test_dbs/br_regression.sqlite3}"
mkdir -p "$_ROOT/.django_test_dbs"
cd "$_ROOT"
echo "[run_br_regression_tests] DJANGO_TEST_DB_FILE=$DJANGO_TEST_DB_FILE"
python manage.py test \
  apps.schools.tests.test_super_beyond_reach \
  apps.compliance.tests.test_attendance_region_br05 \
  apps.compliance.tests.test_enrollment_region_br05 \
  apps.analytics.tests.test_at_risk_intervention_br06 \
  apps.communication.tests.test_thread_locale_retention_br08 \
  apps.communication.tests.test_message_locale_wiring \
  apps.siteconfig.tests.test_tour_steps_control_plane \
  --noinput "$@"
echo "[run_br_regression_tests] OK"
