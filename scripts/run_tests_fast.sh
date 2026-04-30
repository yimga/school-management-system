#!/usr/bin/env bash
# Fast repeat runs: reuse one file-backed SQLite test DB (--keepdb).
# Serial only (RMC_RELIABLE_TEST_RUNNER=1). Pass extra args to manage.py test (e.g. app labels).
#
# Usage:
#   bash scripts/run_tests_fast.sh
#   bash scripts/run_tests_fast.sh apps.config.tests
#
# Env:
#   DJANGO_TEST_DB_FILE — if unset, uses .django_test_dbs/fast_reuse.sqlite3
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

export RMC_RELIABLE_TEST_RUNNER="${RMC_RELIABLE_TEST_RUNNER:-1}"
export DJANGO_TEST_DB_FILE="${DJANGO_TEST_DB_FILE:-${ROOT}/.django_test_dbs/fast_reuse.sqlite3}"
mkdir -p "$(dirname "${DJANGO_TEST_DB_FILE}")"

echo "run_tests_fast: DJANGO_TEST_DB_FILE=${DJANGO_TEST_DB_FILE} ( --keepdb )"
exec python manage.py test --noinput --keepdb "$@"
