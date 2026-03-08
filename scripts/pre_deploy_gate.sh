#!/usr/bin/env bash
# Pre-deploy safety gate: migration check, template compile, smoke + theme matrix.
# Exit 0 only if all pass. Run before deploy or in CI.
set -euo pipefail

echo "[pre_deploy_gate] Django check"
python manage.py check

echo "[pre_deploy_gate] Architecture laws (no hardcoding; lint reports SiteSettings usage)"
python scripts/check_no_hardcoding.py --allow-tests
python scripts/lint_tenant_settings.py --exit-zero

echo "[pre_deploy_gate] Migrations (no unapplied changes)"
python manage.py makemigrations --check --dry-run

echo "[pre_deploy_gate] Tenant model audit"
python manage.py audit_tenant_models --strict

echo "[pre_deploy_gate] Smoke URLs"
python manage.py test apps.accounts.tests.test_smoke_urls -v 1

echo "[pre_deploy_gate] Theme stress matrix"
python manage.py test apps.siteconfig.tests.test_theme_visibility_matrix -v 1

echo "[pre_deploy_gate] Phase checks (targeted tests)"
python manage.py test apps.siteconfig.tests.test_admin_ui_smoke apps.api.tests.test_dashboard_api_rbac -v 1

echo "[pre_deploy_gate] Phase 7 core workflow regression (qa.md, automation.md)"
python manage.py test_core_workflows

echo "[pre_deploy_gate] Multi-tenant coverage checks"
# Run only tests that are committed on main (omit test_global_catalog, test_tenant_audit if not yet merged)
python manage.py test \
  apps.siteconfig.tests.test_education_profile_engine \
  apps.schools.tests.test_feature_registry \
  apps.schools.tests.test_tenant_isolation_and_provisioning \
  -v 1

echo "[pre_deploy_gate] Render startup command sanity"
if ! grep -q "render_start_web.sh" render.yaml; then
  echo "render.yaml must reference scripts/release/render_start_web.sh" >&2
  exit 1
fi
if ! grep -q "render_start_web.sh" Procfile; then
  echo "Procfile must reference scripts/release/render_start_web.sh" >&2
  exit 1
fi

if [[ "${POWERHOUSE_WAVE0_STRICT:-0}" == "1" ]]; then
  echo "[pre_deploy_gate] Powerhouse Wave 0 strict gate"
  bash scripts/release/powerhouse_wave0_gate.sh
fi

echo "[pre_deploy_gate] PASSED"
exit 0
