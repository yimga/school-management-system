#!/usr/bin/env bash
# Pre-deploy safety gate: migration check, template compile, smoke + theme matrix.
# Exit 0 only if all pass. Run before deploy or in CI.
set -euo pipefail

run_django_tests() {
  python manage.py test "$@" --keepdb --noinput -v 1
}

echo "[pre_deploy_gate] No committed .env / .env.local"
bash scripts/check_no_committed_env.sh

echo "[pre_deploy_gate] Repo hygiene (no conflict markers, backup files)"
python scripts/check_repo_hygiene.py

echo "[pre_deploy_gate] Root clutter (generated artifacts must not live at repo root)"
python scripts/check_root_clutter.py

echo "[pre_deploy_gate] Bounded context imports (tenant vs control-plane)"
python scripts/lint_bounded_context_imports.py --strict
python scripts/lint_siteconfig_legacy_imports.py

echo "[pre_deploy_gate] Provider secret exposure"
python scripts/lint_secret_exposure.py

echo "[pre_deploy_gate] Runtime-visible branding residue"
python scripts/lint_gilead_residue.py

echo "[pre_deploy_gate] No print() in application code"
python scripts/lint_no_print_in_apps.py

echo "[pre_deploy_gate] Django check"
python manage.py check

echo "[pre_deploy_gate] Packages and setup_studio migrations applied"
python manage.py showmigrations packages setup_studio | grep -E '^\s+\[ \]' && { echo "Unapplied migrations in packages or setup_studio" >&2; exit 1; } || true

echo "[pre_deploy_gate] Architecture laws (no hardcoding; lint reports SiteSettings usage)"
python scripts/check_no_hardcoding.py --allow-tests
python scripts/lint_tenant_settings.py --check-get-solo-only
python scripts/lint_tenant_settings.py --check-school-settings-features
# Path to 10: report allowlisted get_solo (migration backlog); optional visibility
python scripts/lint_tenant_settings.py --report-allowlisted --base . 2>/dev/null || true
python scripts/generate_platform_inventory.py --check
python scripts/lint_csrf_exempt_usage.py
python scripts/lint_allow_any_usage.py
python scripts/lint_raw_sql_usage.py
python scripts/lint_broad_except.py --allowlist scripts/allowlists/broad_except_allowlist.json --strict
echo "[pre_deploy_gate] Codex guardrails (mega-files)"
if [ "${CODEX_STRICT:-0}" = "1" ]; then
  python scripts/lint_mega_files.py
else
  python scripts/lint_mega_files.py --exit-zero
fi

echo "[pre_deploy_gate] Migrations (no unapplied changes)"
python manage.py makemigrations --check --dry-run

echo "[pre_deploy_gate] Tenant model audit"
python manage.py audit_tenant_models --strict

echo "[pre_deploy_gate] Smoke URLs"
run_django_tests apps.accounts.tests.test_smoke_urls

echo "[pre_deploy_gate] Targeted hardening regressions"
TARGETED_HARDENING_TESTS=(
  apps.siteconfig.tests.test_ai_copilot_context
  apps.siteconfig.tests.test_backend_context
  apps.siteconfig.tests.test_bounded_context_ownership
  apps.siteconfig.tests.test_metadata_catalog
  apps.packages.tests.test_engine
  apps.platform_runtime.tests.test_precedence
  apps.platform_runtime.tests.test_public_api_lints
  apps.portal.tests.test_ai_copilot_config
  apps.portal.tests.test_ai_gateway_smoke
  apps.setup_studio.tests
)
run_django_tests "${TARGETED_HARDENING_TESTS[@]}"

echo "[pre_deploy_gate] Theme stress matrix"
run_django_tests apps.siteconfig.tests.test_theme_visibility_matrix

echo "[pre_deploy_gate] Phase checks (targeted tests)"
run_django_tests apps.siteconfig.tests.test_admin_ui_smoke apps.api.tests.test_dashboard_api_rbac

echo "[pre_deploy_gate] Phase 7 core workflow regression (qa.md, automation.md)"
python manage.py test_core_workflows --keepdb --noinput

echo "[pre_deploy_gate] UX completion audit"
python scripts/verify_ux_completion.py

echo "[pre_deploy_gate] Browser visual QA"
bash scripts/run_visual_qa.sh

echo "[pre_deploy_gate] Multi-tenant coverage checks"
# Run only tests that are committed on main (omit test_global_catalog, test_tenant_audit if not yet merged)
MULTI_TENANT_TESTS=(
  apps.siteconfig.tests.test_education_profile_engine
  apps.schools.tests.test_feature_registry
  apps.schools.tests.test_tenant_isolation_and_provisioning
)
run_django_tests "${MULTI_TENANT_TESTS[@]}"

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

if [[ "${PERF_BUDGET_STRICT:-0}" == "1" ]]; then
  echo "[pre_deploy_gate] Performance budgets (strict)"
  python scripts/check_performance_budgets.py
fi

echo "[pre_deploy_gate] PASSED"
exit 0
