#!/usr/bin/env bash
# Pre-deploy safety gate: migration check, template compile, smoke + theme matrix.
# Exit 0 only if all pass. Run before deploy or in CI.
set -euo pipefail

echo "[pre_deploy_gate] Django check"
python manage.py check

echo "[pre_deploy_gate] Migrations (no unapplied changes)"
python manage.py makemigrations --check --dry-run

echo "[pre_deploy_gate] Smoke URLs"
python manage.py test apps.accounts.tests.test_smoke_urls -v 1

echo "[pre_deploy_gate] Theme stress matrix"
python manage.py test apps.siteconfig.tests.test_theme_visibility_matrix -v 1

echo "[pre_deploy_gate] Phase checks (targeted tests)"
python manage.py test apps.siteconfig.tests.test_admin_ui_smoke apps.api.tests.test_dashboard_api_rbac -v 1

echo "[pre_deploy_gate] PASSED"
exit 0
