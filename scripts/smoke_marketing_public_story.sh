#!/usr/bin/env bash
# Fast marketing smoke: URL resolver + JSON tests + nav contract.
#
# If .env sets DATABASE_URL (Postgres), Django tests would otherwise target Postgres.
# Force repo SQLite for tests, then optional :memory: test DB name:
#   RMC_TEST_LOCAL_SQLITE=1 — ignore DATABASE_URL during tests
#   RMC_SQLITE_TEST_MEMORY=1 — sqlite engine for test runner (see config/settings.py)
#   RMC_SQLITE_TEST_USE_MEMORY_NAME=1 — TEST NAME=:memory: (reduces Windows file locks)
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export RMC_TEST_LOCAL_SQLITE="${RMC_TEST_LOCAL_SQLITE:-1}"
export RMC_SQLITE_TEST_MEMORY="${RMC_SQLITE_TEST_MEMORY:-1}"
export RMC_SQLITE_TEST_USE_MEMORY_NAME="${RMC_SQLITE_TEST_USE_MEMORY_NAME:-1}"
python manage.py validate_marketing_urls --smoke
python manage.py test \
  apps.schools.tests.test_marketing_validation.MarketingContentJsonTests \
  apps.schools.tests.test_marketing_nav_contract \
  --settings=config.settings \
  --noinput
