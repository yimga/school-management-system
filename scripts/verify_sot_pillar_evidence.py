#!/usr/bin/env python3
"""
§0.3.1 — Verify claimed foundation artifacts exist (code + tests + docs).
Fails CI if a [x] pillar dependency path is missing.

Run: ``raise SystemExit(main(None))`` (default ``--base`` is this repository root).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=str(ROOT),
        help="Repository root to inspect (default: this repository root).",
    )
    return parser


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    return _build_parser().parse_args(argv)


def _resolve_base(base: str) -> Path:
    root = Path(base).resolve()
    if not root.is_dir():
        raise ValueError(f"--base path does not exist or is not a directory: {base}")
    return root


def _required_paths(root: Path) -> list[tuple[str, Path]]:
    return [
    ("P1 runtime lint", root / "scripts" / "lint_tenant_settings.py"),
    ("P1 bounded context lint", root / "scripts" / "lint_bounded_context_imports.py"),
    ("P1 residency doc", root / "docs" / "TENANT_ISOLATION_AND_DATA_RESIDENCY.md"),
    (
        "P1 residency test",
        root / "apps" / "schools" / "tests" / "test_school_data_residency_contract.py",
    ),
    ("P2 package engine", root / "apps" / "packages" / "engine.py"),
    (
        "P2 package engine tests",
        root / "apps" / "packages" / "tests" / "test_engine.py",
    ),
    (
        "P2 marketplace minimums test",
        root
        / "apps"
        / "platform_runtime"
        / "tests"
        / "test_marketplace_catalog_minimums.py",
    ),
    ("P2 marketplace review", root / "apps" / "marketplace" / "services.py"),
    ("P2 dev API doc", root / "docs" / "DEVELOPER_PUBLIC_API.md"),
    ("P3 lint_secret_exposure", root / "scripts" / "lint_secret_exposure.py"),
    ("P3 public_endpoint_audit doc", root / "docs" / "public_endpoint_audit.md"),
    ("P4 api v1 manifest", root / "apps" / "api" / "api_v1_manifest.py"),
    (
        "P4 api v1 route contract test",
        root / "apps" / "api" / "tests" / "test_api_v1_route_contract.py",
    ),
    ("P4 oneroster views", root / "apps" / "api" / "oneroster_views.py"),
    ("P5 INTERNAL_API_STANDARDS", root / "docs" / "INTERNAL_API_STANDARDS.md"),
    ("P5 PlatformEventLog model", root / "apps" / "platform_runtime" / "models.py"),
    (
        "P5 platform event test",
        root / "apps" / "platform_runtime" / "tests" / "test_platform_event_log.py",
    ),
    (
        "P5 runtime resolver trace context (GAP.5 partial)",
        root / "apps" / "platform_runtime" / "tracing.py",
    ),
    ("P5 EVENT_DRIVEN_FLOWS", root / "docs" / "EVENT_DRIVEN_FLOWS.md"),
    (
        "P6 Phase H URL tests",
        root / "apps" / "accounts" / "tests" / "test_phase_h_ux_verification.py",
    ),
    ("P7 pre_deploy_gate", root / "scripts" / "pre_deploy_gate.sh"),
    ("Interop trust doc", root / "docs" / "INTEGRATION_PARTNER_TRUST_SIGNALS.md"),
    # §0.3.3 beyond-reach BR evidence (docs + regression tests)
    ("BR SLO doc", root / "docs" / "SLO_TARGETS_AND_OBSERVABILITY.md"),
    ("N16 SOC2/ISO program", root / "docs" / "N16_SOC2_ISO_EXECUTION_PROGRAM.md"),
    ("BR top-20 tasks", root / "docs" / "TOP_20_LOW_CLICK_TASKS.md"),
    ("BR-03 PWA/offline", root / "docs" / "MOBILE_PWA_OFFLINE_BR03.md"),
    (
        "BR-04 migration CSV diff runbook",
        root / "docs" / "MIGRATION_CSV_DIFF_RUNBOOK.md",
    ),
    ("BR-05 live compliance", root / "docs" / "LIVE_COMPLIANCE_VALIDATE_BR05.md"),
    (
        "BR-05 attendance packs",
        root / "apps" / "compliance" / "attendance_region_packs.py",
    ),
    (
        "BR-05 enrollment packs",
        root / "apps" / "compliance" / "enrollment_region_packs.py",
    ),
    ("BR-06 EWS", root / "docs" / "EWS_V1_RUNMY.md"),
    (
        "BR-07/09 super tools test",
        root / "apps" / "schools" / "tests" / "test_super_beyond_reach.py",
    ),
    ("BR-08 comms i18n", root / "docs" / "COMMUNICATION_I18N_POLICY_BR08.md"),
    ("BR-09 Trojan legacy", root / "docs" / "TROJAN_READ_ONLY_LEGACY_BR09.md"),
    ("BR-10 billing SKUs", root / "docs" / "BILLING_SKUS_ENTITLEMENTS_BR10.md"),
    ("BR-12 mega-file plan", root / "docs" / "MEGA_FILE_SPLIT_PLAN_BR12.md"),
    ("Template editing convention", root / "docs" / "TEMPLATE_EDITING_CONVENTION.md"),
    ("BR-13 premium pass", root / "docs" / "PREMIUM_UX_MANUAL_PASS_BR13.md"),
    ("BR audit checklist", root / "docs" / "BR_BEYOND_REACH_AUDIT.md"),
    ("BR-08 comms_locale helper", root / "apps" / "communication" / "comms_locale.py"),
    (
        "BR-08 thread retention cmd",
        root
        / "apps"
        / "communication"
        / "management"
        / "commands"
        / "purge_thread_message_retention.py",
    ),
    (
        "BR-08 message locale wiring test",
        root / "apps" / "communication" / "tests" / "test_message_locale_wiring.py",
    ),
    ("BR regression test runner", root / "scripts" / "run_br_regression_tests.sh"),
    # Wave 25 / N17–N20 — marketplace impact graph + tenant pack install evidence (§0.1.5)
    (
        "N17 package dependency graph JS",
        root / "static" / "js" / "package-dependency-graph.js",
    ),
    (
        "N20 tenant pack install service",
        root / "apps" / "packages" / "tenant_pack_install.py",
    ),
    (
        "N17/N20 tenant package rollback view",
        root / "apps" / "siteconfig" / "views_package_rollback.py",
    ),
    (
        "N17/N20 installed packages rollback template",
        root / "templates" / "siteconfig" / "installed_packages_rollback.html",
    ),
    (
        "N20 tenant pack install tests",
        root / "apps" / "packages" / "tests" / "test_tenant_pack_install.py",
    ),
    (
        "N20 DocumentPack/ExperiencePack version migration",
        root
        / "apps"
        / "packages"
        / "migrations"
        / "0005_documentpack_experiencepack_version.py",
    ),
    ("N24 observability map", root / "docs" / "N24_OBSERVABILITY_AND_ONCALL.md"),
    (
        "SOT §0.1.5 queue status map",
        root / "docs" / "SOT_0155_SECTION_0_1_5_QUEUE_STATUS.md",
    ),
    (
        "Wave 6 roll-call draft wiring test",
        root / "apps" / "portal" / "tests" / "test_roll_call_draft_wiring.py",
    ),
    (
        "RESILIENT_EDGE critical-read JS",
        root / "static" / "js" / "critical-read-degraded.js",
    ),
    (
        "RESILIENT_EDGE wiring test",
        root / "apps" / "portal" / "tests" / "test_resilient_edge_wiring.py",
    ),
    (
        "School CLI resolution (UUID --school for management commands)",
        root / "apps" / "schools" / "school_cli_resolution.py",
    ),
    (
        "N2 parent finance template i18n test",
        root / "apps" / "portal" / "tests" / "test_parent_finance_template_i18n.py",
    ),
    ("N2 parent finance template", root / "templates" / "parent" / "finance.html"),
    (
        "POS fiscal migration",
        root / "apps" / "schoolops" / "migrations" / "0011_possaleline_tax.py",
    ),
    (
        "Compliance erasure template wiring test",
        root / "apps" / "compliance" / "tests" / "test_erasure_template_wiring.py",
    ),
    (
        "Finance form-draft template wiring test",
        root / "apps" / "finance" / "tests" / "test_finance_form_draft_templates.py",
    ),
    (
        "Finance invoice PDF receipt wiring test",
        root / "apps" / "finance" / "tests" / "test_invoice_receipt_pdf.py",
    ),
    (
        "N28 north-star upcoming deadlines API",
        root / "apps" / "api" / "north_star_api_views.py",
    ),
    (
        "N10 performance budget script (pre_deploy_gate)",
        root / "scripts" / "check_performance_budgets.py",
    ),
    (
        "Wave 4 POS tenant ops views",
        root / "apps" / "schoolops" / "views_tenant_ops.py",
    ),
    ("N22 RTL/regional UX doc", root / "docs" / "N22_RTL_AND_REGIONAL_UX.md"),
    (
        "N22 region_settings RTL context test",
        root / "apps" / "siteconfig" / "tests" / "test_n22_region_settings_rtl.py",
    ),
    (
        "BR-12 marketing page definitions split",
        root / "apps" / "schools" / "marketing_page_definitions.py",
    ),
    ("BR-12 super_views constants", root / "apps" / "schools" / "super_views_constants.py"),
    (
        "BR-12 command center data module",
        root / "apps" / "schools" / "super_views_command_center_data.py",
    ),
    (
        "BR-12 command center data test",
        root / "apps" / "schools" / "tests" / "test_super_views_command_center_data.py",
    ),
    (
        "BR-12 command center HTML views module",
        root / "apps" / "schools" / "super_views_command_center_views.py",
    ),
    (
        "BR-12 command center HTML views re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_command_center_views.py",
    ),
    (
        "BR-12 overview surfaces module (schools list + analytics)",
        root / "apps" / "schools" / "super_views_overview_surfaces.py",
    ),
    (
        "BR-12 overview surfaces re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_overview_surfaces.py",
    ),
    (
        "BR-12 super_views dashboard helpers module",
        root / "apps" / "schools" / "super_views_dashboard_helpers.py",
    ),
    (
        "BR-12 super_views dashboard surfaces module",
        root / "apps" / "schools" / "super_views_dashboard_surfaces.py",
    ),
    (
        "BR-12 super_views dashboard surfaces re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_dashboard_surfaces.py",
    ),
    (
        "BR-12 super_views exports module",
        root / "apps" / "schools" / "super_views_exports.py",
    ),
    (
        "BR-12 super_views exports re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_exports.py",
    ),
    (
        "BR-12 super_views geo/plans API module",
        root / "apps" / "schools" / "super_views_geo_api.py",
    ),
    (
        "BR-12 super_views geo API re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_geo_api.py",
    ),
    (
        "BR-12 super_views school lifecycle/policy API module",
        root / "apps" / "schools" / "super_views_school_api.py",
    ),
    (
        "BR-12 super_views school API re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_school_api.py",
    ),
    (
        "BR-12 super_views policy diff module",
        root / "apps" / "schools" / "super_views_policy.py",
    ),
    (
        "BR-12 super_views policy re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_policy.py",
    ),
    (
        "BR-12 super_views trust surface module",
        root / "apps" / "schools" / "super_views_trust_surface.py",
    ),
    (
        "BR-12 super_views trust surface re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_trust_surface.py",
    ),
    (
        "BR-12 super_views support module",
        root / "apps" / "schools" / "super_views_support.py",
    ),
    (
        "BR-12 super_views support re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_support.py",
    ),
    (
        "BR-12 super_views AI module",
        root / "apps" / "schools" / "super_views_ai.py",
    ),
    (
        "BR-12 super_views AI re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_ai.py",
    ),
    (
        "BR-12 super_views impersonation module",
        root / "apps" / "schools" / "super_views_impersonation.py",
    ),
    (
        "BR-12 super_views impersonation re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_impersonation.py",
    ),
    (
        "BR-12 super_views runtime ops module",
        root / "apps" / "schools" / "super_views_runtime_ops.py",
    ),
    (
        "BR-12 super_views runtime ops re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_runtime_ops.py",
    ),
    (
        "BR-12 super_views platform monitoring module",
        root / "apps" / "schools" / "super_views_platform_monitoring.py",
    ),
    (
        "BR-12 super_views platform monitoring re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_platform_monitoring.py",
    ),
    (
        "BR-12 super_views billing console module",
        root / "apps" / "schools" / "super_views_billing_console.py",
    ),
    (
        "BR-12 super_views billing console re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_billing_console.py",
    ),
    (
        "BR-12 super_views create school wizard module",
        root / "apps" / "schools" / "super_views_create_school_wizard.py",
    ),
    (
        "BR-12 super_views create school wizard re-export test",
        root / "apps" / "schools" / "tests" / "test_super_views_create_school_wizard.py",
    ),
    (
        "N23 inclusive terminology and imagery doc",
        root / "docs" / "N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md",
    ),
    (
        "N3 payroll portal table header test",
        root / "apps" / "payroll" / "tests" / "test_payroll_template_table_a11y.py",
    ),
    (
        "N3 misc table header templates (analytics/evals/reports)",
        root / "apps" / "portal" / "tests" / "test_n3_misc_table_header_templates.py",
    ),
    ]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        root = _resolve_base(args.base)
    except ValueError as exc:
        print(f"verify_sot_pillar_evidence: {exc}", file=sys.stderr)
        return 1
    required = _required_paths(root)
    missing = [(label, p) for label, p in required if not p.is_file()]
    if missing:
        for label, p in missing:
            print(f"MISSING [{label}]: {p.relative_to(root)}", file=sys.stderr)
        return 1
    print(f"verify_sot_pillar_evidence: OK ({len(required)} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(None))
