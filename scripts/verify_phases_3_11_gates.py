#!/usr/bin/env python3
"""
Verify repo gates aligned with execution plan Phases 3-11.

Runs linters and static audits; includes `manage.py check` and
`makemigrations --check --dry-run` (no DB apply). Some steps import Django
without requiring migrations. DB-backed tests: see TEST_DATABASE.md and
pre_deploy_gate.sh.

CI: `pre_deploy_gate.sh` exercises the same non-DB steps via
`apps.platform_runtime.tests.test_tenant_settings_lint` (plus additional phase
slices); this script remains the standalone developer entrypoint.

Exit 0 if all steps pass; non-zero on first failure.

Run: ``raise SystemExit(main(None))`` (optional ``--base``; default is this repository root).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

DEFAULT_REPO = Path(__file__).resolve().parents[1]
REPO = DEFAULT_REPO


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(DEFAULT_REPO),
        help="Repository root (defaults to this repository root).",
    )
    return parser.parse_args(argv)


def _resolve_base(raw_base: str) -> Path:
    base = Path(raw_base).resolve()
    if not base.is_dir():
        raise ValueError(f"Base path is not a directory: {base}")
    return base


def _configure_root(base: Path) -> None:
    global REPO
    REPO = base


def _script_path(name: str) -> str:
    return str(REPO / "scripts" / name)


def _manage_path() -> str:
    return str(REPO / "manage.py")


def _repo_path(relative_path: str) -> str:
    return str(REPO / Path(relative_path))


def run(cmd: list[str], label: str) -> None:
    print(f"--- {label} ---", flush=True)
    result = subprocess.run(cmd, cwd=REPO, shell=False)
    if result.returncode != 0:
        print(f"FAILED: {label}", file=sys.stderr)
        sys.exit(result.returncode)
    print(f"OK: {label}\n", flush=True)


def main(argv: list[str] | None = None) -> int:
    try:
        _configure_root(_resolve_base(parse_args(argv).base))
    except ValueError as exc:
        print(f"verify_phases_3_11_gates FAILED: {exc}", file=sys.stderr)
        return 1

    py = sys.executable
    base_args = ["--base", str(REPO)]

    run(
        [py, _script_path("check_no_committed_env.py"), *base_args],
        "Secrets hygiene: no tracked .env / .env.local in git",
    )
    run(
        [py, _script_path("check_repo_hygiene.py"), *base_args],
        "Repo hygiene: conflict markers, backup files (pre-deploy parity)",
    )
    run(
        [py, _script_path("check_root_clutter.py"), *base_args],
        "Root clutter: tracked repo-root files allowlist (pre-deploy parity)",
    )
    run([py, _manage_path(), "check"], "Django system check (pre-deploy parity)")
    run(
        [py, _manage_path(), "makemigrations", "--check", "--dry-run"],
        "Migrations: no model changes without migrations (pre-deploy parity)",
    )
    run(
        [py, _script_path("lint_bounded_context_imports.py"), "--strict", *base_args],
        "Bounded-context imports: tenant vs control-plane surfaces",
    )
    run(
        [py, _script_path("lint_siteconfig_legacy_imports.py"), *base_args],
        "Siteconfig: block legacy imports for domain-owned models",
    )
    run(
        [py, _script_path("scan_repo_secrets.py"), *base_args],
        "High-risk secret-pattern scan (apps/config/services)",
    )
    run(
        [py, _script_path("lint_no_print_in_apps.py"), *base_args],
        "No print() in application code",
    )
    run(
        [py, "-m", "ruff", "check", _repo_path("apps"), "--select", "F401,F841"],
        "Ruff: unused imports / unused variables in apps",
    )
    run(
        [py, _script_path("check_no_hardcoding.py"), "--allow-tests", *base_args],
        "Architecture: check_no_hardcoding (tests exempt where flagged)",
    )
    run(
        [py, _script_path("lint_phase_b_batch3_sitesettings_fk_writes.py"), *base_args],
        "Phase B batch 3: no SiteSettings ORM writes to removed branding FK columns",
    )
    run(
        [
            py,
            _script_path("lint_broad_except.py"),
            "--allowlist",
            _repo_path("scripts/allowlists/broad_except_allowlist.json"),
            "--strict",
            *base_args,
        ],
        "Broad except: allowlist + strict",
    )
    run(
        [py, _script_path("generate_platform_inventory.py"), "--write", *base_args],
        "Platform inventory artifacts refreshed (pre-deploy parity)",
    )
    run(
        [py, _script_path("generate_platform_inventory.py"), "--check", *base_args],
        "Platform inventory JSON matches repo (post-write pre-deploy parity)",
    )
    run(
        [py, _script_path("verify_shell_architecture_matrix.py"), *base_args],
        "Shell triad matrix: marketing/control-plane/admin/tenant contracts",
    )
    run(
        [
            py,
            _script_path("verify_phase2_authenticated_shell_conformance.py"),
            *base_args,
        ],
        "Phase 2: authenticated shell hierarchy and marker conformance",
    )
    run(
        [
            py,
            _script_path("verify_phase3_navigation_command_conformance.py"),
            *base_args,
        ],
        "Phase 3: canonical nav IA and command palette contracts",
    )
    run(
        [
            py,
            _script_path("verify_phase4_control_plane_decision_console.py"),
            *base_args,
        ],
        "Phase 4: decision-console outcome/source/publish contracts",
    )
    run(
        [
            py,
            _script_path("verify_operator_surface_maturity.py"),
            *base_args,
        ],
        "Phase 4: earned-stable operator surface maturity",
    )
    run(
        [
            py,
            _script_path("verify_dashboard_topology_integrity.py"),
            "--write",
            *base_args,
        ],
        "Dual-dashboard topology: RBAC, seed, migration, shell contracts",
    )
    run(
        [
            py,
            _script_path("verify_admin_tenant_change_form_product_links.py"),
            *base_args,
        ],
        "P3: tenant admin change_form templates expose product escape links",
    )
    run(
        [py, _script_path("verify_phase_h_skiplink_targets.py"), *base_args],
        "Phase H depth: base-shell skip-link target integrity",
    )
    run(
        [py, _script_path("generate_gate_map_appendix.py"), "--check", *base_args],
        "Docs appendix drift: gate map generated from single config",
    )
    run(
        [
            py,
            _script_path("verify_api_v1_named_routes_snapshot.py"),
            "--check",
            *base_args,
        ],
        "API v1: named urlpattern list matches scripts/generated/api_v1_named_routes.json",
    )
    run(
        [py, _script_path("verify_operating_discipline_docs.py"), *base_args],
        "Sec 10.5: role_home_engine *_DOC constants resolve under docs/",
    )
    run(
        [py, _script_path("verify_design_system_phase2.py"), *base_args],
        "ZIP Phase 2: design-system CSS/bases + forbidden inline style + Sec 10.5 layer script",
    )
    run(
        [py, _script_path("audit_luxury_ui_surface.py")],
        "Luxury UI surface: high-impact templates + score gate (>= 13/15) + severe integration",
    )
    run(
        [py, _script_path("lint_marketing_nav_no_overflow.py"), *base_args],
        "Marketing header: primary nav count / overflow handling (pre-deploy parity)",
    )
    run(
        [py, _script_path("verify_developer_public_surface.py"), *base_args],
        "Public developer section: runmycampus.com routes, nav, discovery APIs",
    )
    run(
        [py, _script_path("verify_manager_admin_cp_layout.py"), "--css-only", *base_args],
        "Manager /admin/: unified CP layout + main-column scroll contract",
    )
    run(
        [py, _script_path("verify_doc_plan_density_discipline.py"), *base_args],
        "Docs discipline: single-source plan density non-growth",
    )
    run(
        [py, _script_path("verify_dual_plane_theme_experience.py"), *base_args],
        "Theme: tenant + manager dual-plane experience hub surfaces",
    )
    run(
        [py, _script_path("verify_theme_experience_plane_isolation.py"), *base_args],
        "Theme: operator vs tenant plane isolation (builder storage + templates)",
    )
    run(
        [py, _script_path("verify_portal_theme_token_spine.py"), *base_args],
        "Theme: portal token spine (school-primary mixes, no legacy indigo)",
    )
    run(
        [py, _script_path("verify_theme_experience_gear.py"), *base_args],
        "Theme: builder publish/preview APIs, hub hero, append-only bulk guard",
    )
    run(
        [py, _script_path("verify_forensic_master_prompt_completion.py"), *base_args],
        "Forensic: Section 8 master prompt mechanical completion matrix",
    )
    run(
        [py, _script_path("verify_five_pillar_platform_completion.py"), *base_args],
        "Platform: AWS/Shopify/Salesforce/Linux/Google five-pillar completion",
    )
    run(
        [py, _script_path("verify_greatest_education_os_matrix.py"), "--write", *base_args],
        "GEOS-99: greatest education OS matrix (repo axis ≥99%)",
    )
    run(
        [py, _script_path("verify_geos_lane2_scaffold.py"), *base_args],
        "GEOS-99: Lane 2 operator evidence scaffold",
    )
    run(
        [py, _script_path("verify_six_pillar_global_dominance.py"), "--write", *base_args],
        "Platform: six-pillar global dominance (sovereignty + five-pillar + AI + forensic)",
    )
    run(
        [py, _script_path("verify_path_to_100_plan_discipline.py"), *base_args],
        "Per-app depth: PATH_TO_100 plan Sec 6 spine + SOT pointers (slice vs Sec 12 gate)",
    )
    run(
        [py, _script_path("verify_pre_deploy_gate_record.py"), *base_args],
        "Sec 11.4: committed pre_deploy_gate_run.txt success tail + gate-finished when present",
    )
    run(
        [py, _script_path("verify_migration_safety_doc_discipline.py"), *base_args],
        "Sec 0.4: NORTH_STAR migration safety operator contract anchors",
    )
    run(
        [py, _script_path("verify_performance_targets_doc_discipline.py"), *base_args],
        "Sec 0.4: NORTH_STAR performance targets (N9/N10) operator contract anchors",
    )
    run(
        [py, _script_path("verify_lms_sso_doc_discipline.py"), *base_args],
        "Sec 0.4: NORTH_STAR LMS/SSO and federation operator contract anchors",
    )
    run(
        [py, _script_path("verify_uk_international_packs_doc_discipline.py"), *base_args],
        "Sec 0.4: NORTH_STAR UK/international packs operator contract anchors",
    )
    run(
        [py, _script_path("verify_advancement_crm_doc_discipline.py"), *base_args],
        "Sec 0.4: NORTH_STAR advancement CRM operator contract anchors",
    )
    run(
        [py, _script_path("verify_ai_blueprint_completion.py"), *base_args],
        "AI/provider matrix: gateway + prompts + endpoints + docs",
    )
    run(
        [py, _script_path("verify_ai_engine_room.py"), *base_args],
        "AI engine room tiers 1-5: prompt + command bar + product assistants",
    )
    run(
        [py, _script_path("verify_siteconfig_decomposition_depth.py"), *base_args],
        "Siteconfig decomposition: domain_ownership vs Phase B snapshots + slim/first-class artifacts",
    )
    run(
        [
            py,
            _script_path("lint_tenant_settings.py"),
            "--check-get-solo-only",
            *base_args,
        ],
        "Phase 5: lint_tenant_settings",
    )
    run(
        [py, _script_path("verify_phase_5_siteconfig.py"), *base_args],
        "Phase 5 siteconfig dismantling gate (docs + domain_ownership + parity)",
    )
    run(
        [py, _script_path("verify_phase5_studio_os_conformance.py"), *base_args],
        "Phase 5 / Studio OS: five modes, URL routes, legacy redirects, output canvas contracts",
    )
    run(
        [py, _script_path("verify_phase6_runtime_first_conformance.py"), *base_args],
        "Phase 6: runtime-first precedence + fallback-ban contracts",
    )
    run(
        [py, _script_path("verify_phase6_runtime_first_extension.py"), *base_args],
        "Phase 6 extension: allowlisted downstream policy-consumer contracts",
    )
    run(
        [py, _script_path("lint_sitesettings_orm_singleton.py"), *base_args],
        "SiteSettings.objects choke point (models.py + helpers.py only)",
    )
    run(
        [py, _script_path("lint_gilead_residue.py"), *base_args],
        "Phase 11: lint_gilead_residue",
    )
    run(
        [py, _script_path("verify_gilead_full_tree_classification.py"), *base_args],
        "Phase 12 depth: full-tree Gilead references stay in classified buckets",
    )
    run(
        [py, _script_path("lint_csrf_exempt_usage.py"), *base_args],
        "Premium maturity: lint_csrf_exempt_usage (allowlisted)",
    )
    run(
        [py, _script_path("lint_allow_any_usage.py"), *base_args],
        "Premium maturity: lint_allow_any_usage (allowlisted)",
    )
    run(
        [py, _script_path("lint_raw_sql_usage.py"), *base_args],
        "Premium maturity: lint_raw_sql_usage (allowlisted)",
    )
    run(
        [py, _script_path("verify_security_allowlists.py"), *base_args],
        "P0: allowlist JSON manifest_last_reviewed + per-entry last_reviewed + policy dates",
    )
    run(
        [py, _script_path("verify_security_allowlist_density.py"), *base_args],
        "Security non-growth: allowlist density + embedded classification lints + ledger summary parity",
    )
    run(
        [py, _script_path("build_phase8_security_ledger.py"), "--check", *base_args],
        "Phase 8/9 parity: merged security ledger matches allowlists",
    )
    run(
        [py, _script_path("lint_secret_exposure.py"), *base_args],
        "Phase 8: lint_secret_exposure",
    )
    run(
        [py, _script_path("verify_sot_pillar_evidence.py"), *base_args],
        "SOT pillar evidence (cross-phase)",
    )
    run(
        [py, _script_path("validate_wedge_super_premium_phases.py"), *base_args, "--phase", "all"],
        "SOT Sec 0.2.1.5-Sec 0.2.1.6: wedge super-premium phased validation (pre-deploy parity)",
    )
    run(
        [py, _script_path("verify_phase7_dashboard_markers.py"), *base_args],
        "Phase 7/8: registered dashboard templates carry decision-surface + declaration tags",
    )
    run(
        [py, _script_path("verify_control_plane_hub_registry_drift.py"), *base_args],
        "Control plane: hub registry closed (PHASE7 list + exempts cover all CP extends)",
    )
    run(
        [py, _script_path("verify_phase8_dashboard_density.py"), *base_args],
        "Phase 8: high-card Phase 7 templates include de-secondary-collapsible",
    )
    run(
        [py, _script_path("verify_phase_b_snapshot_migration_alignment.py"), *base_args],
        "Siteconfig depth: Phase B snapshot migration alignment",
    )
    run(
        [
            py,
            _script_path("verify_marketplace_integration_first_class_parity.py"),
            *base_args,
        ],
        "Marketplace: integration secrets vs RuntimeDefaults first-class + Phase B strip list",
    )
    run(
        [py, _script_path("verify_structured_logging_contract.py"), *base_args],
        "Observability depth: structured logging contract",
    )
    run(
        [py, _script_path("verify_45_wedge_scorecard.py"), *base_args],
        "Wedge scorecard: 45 rows (Phase 2 tracker)",
    )
    run(
        [py, _script_path("validate_wedges_phase.py"), *base_args, "--phase", "all"],
        "Wedges 1-45: phased execution gate (5x10)",
    )
    run(
        [py, _script_path("verify_wedge_line_registry.py"), *base_args],
        "Wedge line registry: 45 rows + URL reverses + beachhead slugs",
    )
    run(
        [
            py,
            "-m",
            "pytest",
            f"--rootdir={REPO}",
            _repo_path("apps/marketplace/tests/test_marketplace_wedge_coverage.py"),
            "-q",
        ],
        "Marketplace first-party: wedge_ids cover 1-45",
    )
    run(
        [py, _script_path("verify_beachhead_checklists.py"), *base_args],
        "Operator checklists: wedges 1-45",
    )
    run(
        [py, _script_path("phase_h_audit.py"), *base_args],
        "Phase 8: phase_h_audit (static)",
    )
    run(
        [py, _script_path("lint_north_star_a11y.py"), "--strict", *base_args],
        "North star: accessibility.css on base shells (strict)",
    )
    run(
        [py, _script_path("lint_north_star_i18n.py"), "--strict", *base_args],
        "North star: i18n load on key templates (strict)",
    )
    run(
        [py, _script_path("verify_i18n_catalog_fresh.py"), *base_args],
        "i18n: en django.po covers scanned translatable strings (pre-deploy parity)",
    )
    run(
        [py, _script_path("verify_program_phase10_phase11_gates.py"), *base_args],
        "Program Phase 10 (ecosystem) + Phase 11 (marketing narrative) static gates",
    )
    run(
        [py, _script_path("verify_repo_wide_ecosystem_marketing_audit.py"), *base_args],
        "Repo-wide Phase 10/11 inventory + spine audit (apps, templates, urls, routing glue)",
    )
    run(
        [py, _script_path("verify_ui_wiring_audit.py"), *base_args],
        "UI wiring: template {% url %} literals vs urlconf union + href hazard scan",
    )
    run(
        [py, _script_path("verify_theme_visibility_platform.py"), *base_args],
        "Theme visibility: shell CSS wiring + manager render smoke",
    )
    run(
        [py, _script_path("verify_backend_base_shell_routing.py"), *base_args],
        "Manager shell: backend_base router + CP smoke probes",
    )
    run(
        [py, _script_path("verify_glocal_closeout_completion.py"), *base_args],
        "Glocal closeout: G-01..G-22 repo proofs + i18n/money-float sub-gates",
    )
    run(
        [py, _script_path("verify_online_edge_dual_mode.py"), *base_args],
        "Online + edge dual-mode: offline bundle, hub docs, portal config",
    )
    run(
        [py, _script_path("verify_page_fold_standards.py"), "--write", *base_args],
        "Page fold: 4-fold cap, back-to-top, task pagination markers",
    )
    run(
        [py, _script_path("verify_footer_surface_contract.py"), "--write", *base_args],
        "Footer surface: operator-compact vs tenant vs marketing",
    )
    run(
        [py, _script_path("verify_platform_chromatic_compliance.py")],
        "Platform chromatic: tables, list-groups, manager light bleed, marketplace proof",
    )
    run(
        [py, _script_path("scan_main_content_text_utilities.py"), *base_args],
        "Theme visibility: main-content text-white/text-dark baseline",
    )
    print("verify_phases_3_11_gates: all non-DB gates passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
