#!/usr/bin/env bash
set -euo pipefail

echo "[smoke] django system check"
python manage.py check

echo "[smoke] core security and workflow smoke tests"
python manage.py test \
  apps.accounts.tests.test_access_smoke \
  apps.accounts.tests.test_permissions_hierarchy \
  apps.requests.tests.test_views_security \
  apps.finance.tests.test_phase0_security \
  -v 1

echo "[smoke] complete"
