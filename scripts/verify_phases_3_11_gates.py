#!/usr/bin/env python3
"""
Verify repo gates aligned with execution plan Phases 3–11 (control plane → Gilead/docs).

Runs linters and static audits; includes `manage.py check` and
``makemigrations --check --dry-run`` (no DB apply). Some steps (e.g. wedge
super-premium URL reverse) import Django without requiring migrations.
DB-backed tests: see TEST_DATABASE.md and pre_deploy_gate.sh.

CI: ``pre_deploy_gate.sh`` exercises the same non-DB steps via
``apps.platform_runtime.tests.test_tenant_settings_lint`` (plus additional phase slices);
this script remains the standalone developer entrypoint.

Exit 0 if all steps pass; non-zero on first failure.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def run(cmd: list[str], label: str) -> None:
    print(f"--- {label} ---", flush=True)
    r = subprocess.run(
        cmd,
        cwd=REPO,
        shell=False,
    )
    if r.returncode != 0:
        print(f"FAILED: {label}", file=sys.stderr)
        sys.exit(r.returncode)
    print(f"OK: {label}\n", flush=True)


def main() -> None:
    py = sys.executable
    run([py, "scripts/check_no_committed_env.py"], "Secrets hygiene: no tracked .env / .env.local in git")
    run([py, "scripts/check_repo_hygiene.py"], "Repo hygiene: conflict markers, backup files (pre-deploy parity)")
    run([py, "scripts/check_root_clutter.py"], "Root clutter: tracked repo-root files allowlist (pre-deploy parity)")
    run([py, "manage.py", "check"], "Django system check (pre-deploy parity)")
    run(
        [py, "manage.py", "makemigrations", "--check", "--dry-run"],
        "Migrations: no model changes without migrations (pre-deploy parity)",
    )
    run(
        [py, "scripts/lint_bounded_context_imports.py", "--strict"],
        "Bounded-context imports: tenant vs control-plane surfaces",
    )
    run(
        [py, "scripts/lint_siteconfig_legacy_imports.py"],
        "Siteconfig: block legacy imports for domain-owned models",
    )
    run(
        [py, "scripts/scan_repo_secrets.py"],
        "High-risk secret-pattern scan (apps/config/services)",
    )
    run([py, "scripts/lint_no_print_in_apps.py"], "No print() in application code")
    run(
        [py, "-m", "ruff", "check", "apps", "--select", "F401,F841"],
        "Ruff: unused imports / unused variables in apps",
    )
    run(
        [py, "scripts/check_no_hardcoding.py", "--allow-tests"],
        "Architecture: check_no_hardcoding (tests exempt where flagged)",
    )
    run(
        [py, "scripts/lint_phase_b_batch3_sitesettings_fk_writes.py"],
        "Phase B batch 3: no SiteSettings ORM writes to removed branding FK columns",
    )
    run(
        [
            py,
            "scripts/lint_broad_except.py",
            "--allowlist",
            "scripts/allowlists/broad_except_allowlist.json",
            "--strict",
        ],
        "Broad except: allowlist + strict",
    )
    run(
        [py, "scripts/generate_platform_inventory.py", "--check"],
        "Platform inventory JSON matches repo (--check only; no --write)",
    )
    run([py, "scripts/verify_shell_architecture_matrix.py"], "Shell triad matrix: marketing/control-plane/admin/tenant contracts")
    run(
        [py, "scripts/verify_admin_tenant_change_form_product_links.py"],
        "P3: tenant admin change_form templates expose product escape links",
    )
    run([py, "scripts/verify_phase_h_skiplink_targets.py"], "Phase H depth: base-shell skip-link target integrity")
    run(
        [py, "scripts/generate_gate_map_appendix.py", "--check"],
        "Docs appendix drift: gate map generated from single config",
    )
    run(
        [py, "scripts/verify_api_v1_named_routes_snapshot.py", "--check"],
        "API v1: named urlpattern list matches scripts/generated/api_v1_named_routes.json",
    )
    run(
        [py, "scripts/verify_operating_discipline_docs.py"],
        "§10.5: role_home_engine *_DOC constants resolve under docs/",
    )
    run(
        [py, "scripts/verify_design_system_phase2.py"],
        "ZIP Phase 2: design-system CSS/bases + forbidden inline style + §10.5 layer script",
    )
    run(
        [py, "scripts/lint_marketing_nav_no_overflow.py"],
        "Marketing header: primary nav count / overflow handling (pre-deploy parity)",
    )
    run(
        [py, "scripts/verify_doc_plan_density_discipline.py"],
        "Docs discipline: single-source plan density non-growth",
    )
    run(
        [py, "scripts/verify_path_to_100_plan_discipline.py"],
        "Per-app depth: PATH_TO_100 plan §6 spine + SOT pointers (slice vs §12 gate)",
    )
    run(
        [py, "scripts/verify_pre_deploy_gate_record.py"],
        "§11.4: committed pre_deploy_gate_run.txt success tail + gate-finished when present",
    )
    run(
        [py, "scripts/verify_migration_safety_doc_discipline.py"],
        "§0.4: NORTH_STAR migration safety operator contract anchors",
    )
    run(
        [py, "scripts/verify_performance_targets_doc_discipline.py"],
        "§0.4: NORTH_STAR performance targets (N9/N10) operator contract anchors",
    )
    run(
        [py, "scripts/verify_lms_sso_doc_discipline.py"],
        "§0.4: NORTH_STAR LMS/SSO & federation operator contract anchors",
    )
    run(
        [py, "scripts/verify_uk_international_packs_doc_discipline.py"],
        "§0.4: NORTH_STAR UK/international packs operator contract anchors",
    )
    run(
        [py, "scripts/verify_advancement_crm_doc_discipline.py"],
        "§0.4: NORTH_STAR advancement CRM operator contract anchors",
    )
    run([py, "scripts/verify_ai_blueprint_completion.py"], "AI/provider matrix: gateway + prompts + endpoints + docs")
    run(
        [py, "scripts/verify_siteconfig_decomposition_depth.py"],
        "Siteconfig decomposition: domain_ownership vs Phase B snapshots + slim/first-class artifacts",
    )
    run([py, "scripts/lint_tenant_settings.py", "--check-get-solo-only"], "Phase 5: lint_tenant_settings")
    run(
        [py, "scripts/verify_phase_5_siteconfig.py"],
        "Phase 5 siteconfig dismantling gate (docs + domain_ownership + parity)",
    )
    run(
        [py, "scripts/verify_phase5_studio_os_conformance.py"],
        "Phase 5 / Studio OS: five modes, URL routes, legacy redirects, output canvas contracts",
    )
    run(
        [py, "scripts/lint_sitesettings_orm_singleton.py", "--base", "."],
        "SiteSettings.objects choke point (models.py + helpers.py only)",
    )
    run([py, "scripts/lint_gilead_residue.py"], "Phase 11: lint_gilead_residue")
    run(
        [py, "scripts/verify_gilead_full_tree_classification.py"],
        "Phase 12 depth: full-tree Gilead references stay in classified buckets",
    )
    run([py, "scripts/lint_csrf_exempt_usage.py"], "Premium maturity: lint_csrf_exempt_usage (allowlisted)")
    run([py, "scripts/lint_allow_any_usage.py"], "Premium maturity: lint_allow_any_usage (allowlisted)")
    run([py, "scripts/lint_raw_sql_usage.py"], "Premium maturity: lint_raw_sql_usage (allowlisted)")
    run(
        [py, "scripts/verify_security_allowlists.py"],
        "P0: allowlist JSON manifest_last_reviewed + per-entry last_reviewed + policy dates",
    )
    run(
        [py, "scripts/verify_security_allowlist_density.py"],
        "Security non-growth: allowlist density + embedded classification lints + ledger summary parity",
    )
    run(
        [py, "scripts/build_phase8_security_ledger.py", "--check"],
        "Phase 8/9 parity: merged security ledger matches allowlists",
    )
    run([py, "scripts/lint_secret_exposure.py"], "Phase 8: lint_secret_exposure")
    run([py, "scripts/verify_sot_pillar_evidence.py"], "SOT pillar evidence (cross-phase)")
    run(
        [py, "scripts/validate_wedge_super_premium_phases.py", "--phase", "all"],
        "SOT §0.2.1.5–§0.2.1.6: wedge super-premium phased validation (pre-deploy parity)",
    )
    run(
        [py, "scripts/verify_phase7_dashboard_markers.py"],
        "Phase 7/8: registered dashboard templates carry decision-surface + declaration tags",
    )
    run(
        [py, "scripts/verify_control_plane_hub_registry_drift.py"],
        "Control plane: hub registry closed (PHASE7 list + exempts cover all CP extends)",
    )
    run(
        [py, "scripts/verify_phase8_dashboard_density.py"],
        "Phase 8: high-card Phase 7 templates include de-secondary-collapsible",
    )
    run(
        [py, "scripts/verify_phase_b_snapshot_migration_alignment.py"],
        "Siteconfig depth: Phase B snapshot migration alignment",
    )
    run(
        [py, "scripts/verify_marketplace_integration_first_class_parity.py"],
        "Marketplace: integration secrets vs RuntimeDefaults first-class + Phase B strip list",
    )
    run(
        [py, "scripts/verify_structured_logging_contract.py"],
        "Observability depth: structured logging contract",
    )
    run([py, "scripts/verify_45_wedge_scorecard.py"], "Wedge scorecard: 45 rows (Phase 2 tracker)")
    run(
        [py, "scripts/validate_wedges_phase.py", "--phase", "all"],
        "Wedges 1–45: phased execution gate (5×10)",
    )
    run([py, "scripts/verify_wedge_line_registry.py"], "Wedge line registry: 45 rows + URL reverses + beachhead slugs")
    run(
        [
            py,
            "-m",
            "pytest",
            "apps/marketplace/tests/test_marketplace_wedge_coverage.py",
            "-q",
        ],
        "Marketplace first-party: wedge_ids cover 1–45",
    )
    run([py, "scripts/verify_beachhead_checklists.py"], "Operator checklists: wedges 1–45")
    run([py, "scripts/phase_h_audit.py"], "Phase 8: phase_h_audit (static)")
    run(
        [py, "scripts/lint_north_star_a11y.py", "--strict"],
        "North star: accessibility.css on base shells (strict)",
    )
    run(
        [py, "scripts/lint_north_star_i18n.py", "--strict"],
        "North star: i18n load on key templates (strict)",
    )
    run(
        [py, "scripts/verify_i18n_catalog_fresh.py"],
        "i18n: en django.po covers scanned translatable strings (pre-deploy parity)",
    )
    run(
        [py, "scripts/verify_program_phase10_phase11_gates.py"],
        "Program Phase 10 (ecosystem) + Phase 11 (marketing narrative) static gates",
    )
    run(
        [py, "scripts/verify_repo_wide_ecosystem_marketing_audit.py"],
        "Repo-wide Phase 10/11 inventory + spine audit (apps, templates, urls, routing glue)",
    )
    run(
        [py, "scripts/verify_ui_wiring_audit.py"],
        "UI wiring: template {% url %} literals vs urlconf union + href hazard scan",
    )
    print("verify_phases_3_11_gates: all non-DB gates passed.")


if __name__ == "__main__":
    main()
