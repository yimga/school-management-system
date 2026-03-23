#!/usr/bin/env bash
# Run §0.2.1.6 wedge super-premium validators + tests reliably (esp. Windows: avoid locked default.sqlite3).
# From repo root: bash scripts/run_wedge_super_premium_gates.sh
set -euo pipefail
_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
cd "$_REPO_ROOT"

export DJANGO_TEST_DB_FILE="${DJANGO_TEST_DB_FILE:-$_REPO_ROOT/.django_test_dbs/wedge_super_premium_gates.sqlite3}"

echo "[wedge_gates] validate_wedge_world_class.py"
python scripts/validate_wedge_world_class.py

echo "[wedge_gates] validate_wedge_super_premium_phases.py --phase all"
python scripts/validate_wedge_super_premium_phases.py --phase all

echo "[wedge_gates] migrate gate test DB (for TestCase modules)"
python scripts/migrate_gate_test_db.py

echo "[wedge_gates] Django tests (SimpleTestCase + world-class TestCase, --keepdb)"
python manage.py test \
  apps.schools.tests.test_wedge_super_premium_phases \
  apps.schools.tests.test_wedge_world_class_implemented \
  --keepdb --noinput -v 1

echo "[wedge_gates] OK"
