#!/usr/bin/env bash
# Agent 6 — Offline & global payments verification gate (matches mission RUN block).
# Uses file-backed SQLite test DB so --keepdb works; avoids WinError 32 on default.sqlite3
# when another process holds it — override path:
#   export DJANGO_TEST_DB_FILE=".django_test_dbs/my_agent6.sqlite3"
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export DJANGO_TEST_DB_FILE="${DJANGO_TEST_DB_FILE:-.django_test_dbs/agent6_gate.sqlite3}"
python manage.py test \
  apps.platform_runtime.tests.test_offline_queue \
  apps.finance.tests \
  apps.billing.tests \
  --settings=config.settings \
  --noinput \
  --keepdb
python scripts/audit_tenant_isolation.py
python scripts/audit_security_surface.py
echo "run_agent6_offline_payments_gate: OK"
