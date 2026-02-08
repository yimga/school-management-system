#!/usr/bin/env bash
set -euo pipefail

echo "[phase-checks] python manage.py check"
python manage.py check

echo "[phase-checks] baseline targeted tests"
python manage.py test apps.siteconfig.tests.test_admin_ui_smoke apps.api.tests.test_dashboard_api_rbac -v 1

echo "[phase-checks] complete"
