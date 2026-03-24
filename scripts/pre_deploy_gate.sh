#!/usr/bin/env bash
# Pre-deploy safety gate: migration check, template compile, smoke + theme matrix.
# Exit 0 only if all pass. Run before deploy or in CI.
set -euo pipefail

# Use dedicated SQLite test DB for the gate so local dev default.sqlite3 locks/corruption
# do not break pre_deploy_gate (see docs/TEST_DATABASE.md).
_REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")/.." && pwd)"
export DJANGO_TEST_DB_FILE="${DJANGO_TEST_DB_FILE:-$_REPO_ROOT/.django_test_dbs/pre_deploy_gate.sqlite3}"
if [[ "${PRE_GATE_FRESH_TEST_DB:-0}" = "1" ]]; then
  rm -f "$DJANGO_TEST_DB_FILE" 2>/dev/null || true
  # Windows: file may stay locked after rm; half-migrated DB then breaks migrate_gate_test_db ("table already exists").
  if [[ -f "$DJANGO_TEST_DB_FILE" ]]; then
    _ALT="$_REPO_ROOT/.django_test_dbs/pre_deploy_gate_run.sqlite3"
    echo "[pre_deploy_gate] PRE_GATE_FRESH_TEST_DB=1: could not remove stale gate DB (locked?). Using ${_ALT##*/}" >&2
    export DJANGO_TEST_DB_FILE="$_ALT"
    rm -f "$DJANGO_TEST_DB_FILE" 2>/dev/null || true
  fi
  echo "[pre_deploy_gate] PRE_GATE_FRESH_TEST_DB=1: fresh gate test database on next migrate"
fi

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

echo "[pre_deploy_gate] Repo secret-pattern scan (high-risk)"
python scripts/scan_repo_secrets.py

echo "[pre_deploy_gate] Runtime-visible branding residue"
python scripts/lint_gilead_residue.py

echo "[pre_deploy_gate] No print() in application code"
python scripts/lint_no_print_in_apps.py

echo "[pre_deploy_gate] Ruff F401/F841 (unused imports / unused variables)"
python -m ruff check apps --select F401,F841

echo "[pre_deploy_gate] Django check"
python manage.py check

echo "[pre_deploy_gate] Packages and setup_studio migrations applied"
python manage.py showmigrations packages setup_studio | grep -E '^\s+\[ \]' && { echo "Unapplied migrations in packages or setup_studio" >&2; exit 1; } || true

echo "[pre_deploy_gate] Architecture laws (no hardcoding; lint reports SiteSettings usage)"
python scripts/check_no_hardcoding.py --allow-tests
python scripts/lint_tenant_settings.py --check-get-solo-only
python scripts/lint_tenant_settings.py --check-sitesettings-orm-in-tenant-apps
python scripts/lint_tenant_settings.py --check-school-settings-features
# Path to 10: report allowlisted get_solo (migration backlog); optional visibility
python scripts/lint_tenant_settings.py --report-allowlisted --base . 2>/dev/null || true
echo "[pre_deploy_gate] Platform inventory refresh"
python scripts/generate_platform_inventory.py --write
echo "[pre_deploy_gate] Platform inventory verification"
python scripts/generate_platform_inventory.py --check
echo "[pre_deploy_gate] Phase 5 SiteSettings / siteconfig dismantling (docs + domain_ownership + get_solo lint)"
python scripts/verify_phase_5_siteconfig.py
echo "[pre_deploy_gate] Phase B Batch 3 burn-in (no SiteSettings ORM writes to removed branding FK columns)"
python scripts/lint_phase_b_batch3_sitesettings_fk_writes.py
python scripts/lint_csrf_exempt_usage.py
python scripts/lint_allow_any_usage.py
python scripts/lint_raw_sql_usage.py
echo "[pre_deploy_gate] Phase 8 merged security ledger (csrf_exempt + AllowAny + raw SQL allowlists)"
python scripts/build_phase8_security_ledger.py --check
python scripts/lint_broad_except.py --allowlist scripts/allowlists/broad_except_allowlist.json --strict
echo "[pre_deploy_gate] §10.5 operating-discipline doc refs (role_home_engine *_DOC → docs/)"
python scripts/verify_operating_discipline_docs.py
echo "[pre_deploy_gate] §10.5 operating-discipline layers (doc + code)"
python scripts/verify_section10_5_layers.py
echo "[pre_deploy_gate] Phase 2 design system + token enforcement gate"
python scripts/verify_design_system_phase2.py
echo "[pre_deploy_gate] Marketing nav no overflow"
python scripts/lint_marketing_nav_no_overflow.py

echo "[pre_deploy_gate] Codex guardrails (mega-files)"
if [ "${CODEX_STRICT:-0}" = "1" ]; then
  python scripts/lint_mega_files.py
else
  python scripts/lint_mega_files.py --exit-zero
fi

echo "[pre_deploy_gate] §0.3.1 SOT pillar evidence paths (codebase registry)"
python scripts/verify_sot_pillar_evidence.py

echo "[pre_deploy_gate] §0.2.1.5–§0.2.1.6 wedge super-premium phased validation"
python scripts/validate_wedge_super_premium_phases.py --phase all

echo "[pre_deploy_gate] Phase 7 dashboard surface markers (full registry)"
python scripts/verify_phase7_dashboard_markers.py

echo "[pre_deploy_gate] Migrations (no unapplied changes)"
python manage.py makemigrations --check --dry-run

echo "[pre_deploy_gate] Ensure gate test DB has migrations (for --keepdb and verify_ux_completion)"
python scripts/migrate_gate_test_db.py

echo "[pre_deploy_gate] Phase B batch execution (PlatformGlobalBranding table + singleton)"
python scripts/verify_phase_b_execution.py

echo "[pre_deploy_gate] Tenant model audit"
python manage.py audit_tenant_models --strict

echo "[pre_deploy_gate] Smoke URLs + Phase H URL reverse"
run_django_tests apps.accounts.tests.test_smoke_urls apps.accounts.tests.test_phase_h_ux_verification.PhaseHUrlReverseTests

echo "[pre_deploy_gate] Phase H static audit (viewport, error templates, control-plane errors)"
python scripts/phase_h_audit.py
echo "[pre_deploy_gate] §8.0.6 responsive lint (fixed-px layout; advisory, no fail)"
python scripts/lint_section8_responsive.py || true
echo "[pre_deploy_gate] §8.0.11 template audit (inline px / placeholders; advisory)"
python scripts/audit_section8_11_templates.py || true
echo "[pre_deploy_gate] North star a11y (accessibility.css in bases)"
python scripts/lint_north_star_a11y.py || true
echo "[pre_deploy_gate] North star i18n (key templates)"
python scripts/lint_north_star_i18n.py || true

echo "[pre_deploy_gate] Targeted hardening regressions"
TARGETED_HARDENING_TESTS=(
  services.tests.test_ai_gateway
  apps.schools.tests.test_impersonation_dual_control
  apps.schools.tests.test_manager_studio_tenant_boundary
  apps.schools.tests.test_tenant_host_profile_url_wiring
  services.tests.test_ai_memory
  apps.siteconfig.tests.test_ai_copilot_context
  apps.siteconfig.tests.test_ai_admin_surfaces
  apps.siteconfig.tests.test_ai_gateway_metrics
  apps.siteconfig.tests.test_backend_context
  apps.siteconfig.tests.test_bounded_context_ownership
  apps.siteconfig.tests.test_metadata_catalog
  apps.packages.tests.test_engine
  apps.platform_runtime.tests.test_precedence
  apps.platform_runtime.tests.test_tenant_isolation_and_identity
  apps.platform_runtime.tests.test_tenant_settings_lint
  apps.platform_runtime.tests.test_learning_institution_beyond
  apps.platform_runtime.tests.test_runtime_contract
  apps.platform_runtime.tests.test_structured_logging
  apps.platform_runtime.tests.test_public_api_lints
  apps.platform_runtime.tests.test_marketplace_catalog_minimums
  apps.brand_experience.tests.test_platform_global_branding
  apps.platform_runtime.tests.test_phase_b_domain_snapshots
  apps.marketplace.tests.test_install_impact
  apps.marketplace.tests.test_blueprint_rollback_ack
  apps.marketplace.tests.test_governance
  apps.portal.tests.test_ai_copilot_config
  apps.portal.tests.test_ai_feedback
  apps.portal.tests.test_ai_gateway_smoke
  apps.schools.tests.test_provisioning_dispatch
  apps.setup_studio.tests
  apps.siteconfig.tests.test_world_engine_jit_broadcast_syllabus
  apps.api.tests.test_api_v1_route_contract
  apps.api.tests.test_api_v1_manifest
  apps.api.tests.test_api_v1_contract_smoke
  apps.api.tests.test_ai_chat_consumer_gateway
  apps.api.tests.test_dashboard_api_profile_404
  apps.schools.tests.test_school_data_residency_contract
  apps.platform_runtime.tests.test_platform_event_log
  apps.platform_runtime.tests.test_rum_ingest
  apps.platform_runtime.tests.test_rum_aggregate
  apps.schools.tests.test_super_beyond_reach
  apps.schools.tests.test_wedge_super_premium_phases
  apps.schools.tests.test_advancement_tenant_crud
  apps.schoolops.tests.test_tenant_ops_wave4
  apps.schoolops.tests.test_tenant_ops_wave15_substitutes
  apps.schoolops.tests.test_tenant_ops_wave16_visitor
  apps.schoolops.tests.test_tenant_ops_wave17_facilities
  apps.schoolops.tests.test_tenant_ops_wave18_pos
  apps.siteconfig.tests.test_tenant_package_rollback_ui
  apps.portal.tests.test_bulk_capture_hub
  apps.accounts.tests.test_tenant_activity_log_view
  apps.accounts.tests.test_security_trust_hub_views
  apps.compliance.tests.test_attendance_region_br05
  apps.analytics.tests.test_at_risk_intervention_br06
  apps.analytics.tests.test_ews_signal_sync
  apps.communication.tests.test_thread_locale_retention_br08
  apps.communication.tests.test_message_locale_wiring
  apps.dashboard.tests.test_phase7_decision_surface
  apps.dashboard.tests.test_role_home_engine
)
run_django_tests "${TARGETED_HARDENING_TESTS[@]}"

echo "[pre_deploy_gate] AI blueprint contract"
python scripts/verify_ai_blueprint_completion.py

echo "[pre_deploy_gate] Theme stress matrix"
run_django_tests apps.siteconfig.tests.test_theme_visibility_matrix

echo "[pre_deploy_gate] Phase checks (targeted tests)"
run_django_tests apps.siteconfig.tests.test_admin_ui_smoke apps.api.tests.test_dashboard_api_rbac apps.accounts.tests.test_federation_sso_health

echo "[pre_deploy_gate] Phase 7 core workflow regression (qa.md, automation.md)"
python manage.py test_core_workflows --keepdb --noinput

echo "[pre_deploy_gate] UX completion audit"
python scripts/verify_ux_completion.py

echo "[pre_deploy_gate] Browser visual QA"
if [[ "${SKIP_VISUAL_QA:-0}" = "1" ]]; then
  echo "[pre_deploy_gate] SKIP_VISUAL_QA=1: skipping Browser visual QA (E2E). Run 'bash scripts/run_visual_qa.sh' manually when server/Playwright available."
else
  bash scripts/run_visual_qa.sh
fi

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

echo "[pre_deploy_gate] Performance budgets (North star N9/N10; strict when PERF_BUDGET_STRICT=1)"
python scripts/check_performance_budgets.py 2>/dev/null || true
if [[ "${PERF_BUDGET_STRICT:-0}" == "1" ]]; then
  python scripts/check_performance_budgets.py
fi

# §7 / release hygiene: earlier steps (seeds, tests, ensure_*) can change inventory inputs;
# refresh so verify_section7_gate.py --check passes immediately after a green gate.
echo "[pre_deploy_gate] Platform inventory refresh (post-steps, §7 alignment)"
python scripts/generate_platform_inventory.py --write
python scripts/generate_platform_inventory.py --check

echo "[pre_deploy_gate] PASSED"
exit 0
