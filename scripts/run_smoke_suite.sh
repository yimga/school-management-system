#!/usr/bin/env bash
set -euo pipefail

run_django_tests() {
  python manage.py test "$@" --keepdb --noinput -v 1
}

echo "[smoke] django system check"
python manage.py check

echo "[smoke] core security and workflow smoke tests"
run_django_tests \
  apps.accounts.tests.test_access_smoke \
  apps.accounts.tests.test_permissions_hierarchy \
  apps.requests.tests.test_views_security \
  apps.finance.tests.test_phase0_security

echo "[smoke] complete"
