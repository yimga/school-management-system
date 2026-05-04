#!/usr/bin/env bash
# Full marketing story contract: TestCase HTTP checks (apps.schools.tests.test_marketing_public_story_reset).
#
# Requires SQLite test DB (not Postgres from DATABASE_URL). First cold run applies the full
# migration graph and can take ~15–25 minutes; subsequent runs reuse schema if you use a
# dedicated DJANGO_TEST_DB_FILE + --keepdb (see docs/TEST_DATABASE.md).
#
# Usage:
#   bash scripts/smoke_marketing_public_story_full.sh
#   bash scripts/smoke_marketing_public_story_full.sh --keepdb -v 2
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
export RMC_TEST_LOCAL_SQLITE="${RMC_TEST_LOCAL_SQLITE:-1}"
export RMC_SQLITE_TEST_MEMORY="${RMC_SQLITE_TEST_MEMORY:-1}"
export RMC_SQLITE_TEST_USE_MEMORY_NAME="${RMC_SQLITE_TEST_USE_MEMORY_NAME:-1}"
exec python manage.py test apps.schools.tests.test_marketing_public_story_reset \
  --settings=config.settings \
  --noinput \
  "$@"
