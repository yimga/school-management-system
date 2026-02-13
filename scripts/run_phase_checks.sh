#!/usr/bin/env bash
set -euo pipefail

echo "[phase-checks] python manage.py check"
python manage.py check

echo "[phase-checks] baseline targeted tests"
python manage.py test apps.siteconfig.tests.test_admin_ui_smoke apps.api.tests.test_dashboard_api_rbac -v 1

echo "[phase-checks] theme stress matrix"
python manage.py test apps.siteconfig.tests.test_theme_visibility_matrix -v 1

echo "[phase-checks] design token lint (advisory: use --allow-violations to not block)"
python scripts/lint_design_tokens.py --allow-violations || true

echo "[phase-checks] complete"
