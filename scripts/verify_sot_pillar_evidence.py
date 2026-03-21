#!/usr/bin/env python3
"""
§0.3.1 — Verify claimed foundation artifacts exist (code + tests + docs).
Fails CI if a [x] pillar dependency path is missing. Run: python scripts/verify_sot_pillar_evidence.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED: list[tuple[str, Path]] = [
    ("P1 runtime lint", ROOT / "scripts" / "lint_tenant_settings.py"),
    ("P1 bounded context lint", ROOT / "scripts" / "lint_bounded_context_imports.py"),
    ("P1 residency doc", ROOT / "docs" / "TENANT_ISOLATION_AND_DATA_RESIDENCY.md"),
    (
        "P1 residency test",
        ROOT / "apps" / "schools" / "tests" / "test_school_data_residency_contract.py",
    ),
    ("P2 package engine", ROOT / "apps" / "packages" / "engine.py"),
    (
        "P2 package engine tests",
        ROOT / "apps" / "packages" / "tests" / "test_engine.py",
    ),
    (
        "P2 marketplace minimums test",
        ROOT
        / "apps"
        / "platform_runtime"
        / "tests"
        / "test_marketplace_catalog_minimums.py",
    ),
    ("P2 marketplace review", ROOT / "apps" / "marketplace" / "services.py"),
    ("P2 dev API doc", ROOT / "docs" / "DEVELOPER_PUBLIC_API.md"),
    ("P3 lint_secret_exposure", ROOT / "scripts" / "lint_secret_exposure.py"),
    ("P3 public_endpoint_audit doc", ROOT / "docs" / "public_endpoint_audit.md"),
    ("P4 api v1 manifest", ROOT / "apps" / "api" / "api_v1_manifest.py"),
    (
        "P4 api v1 route contract test",
        ROOT / "apps" / "api" / "tests" / "test_api_v1_route_contract.py",
    ),
    ("P4 oneroster views", ROOT / "apps" / "api" / "oneroster_views.py"),
    ("P5 INTERNAL_API_STANDARDS", ROOT / "docs" / "INTERNAL_API_STANDARDS.md"),
    ("P5 PlatformEventLog model", ROOT / "apps" / "platform_runtime" / "models.py"),
    (
        "P5 platform event test",
        ROOT / "apps" / "platform_runtime" / "tests" / "test_platform_event_log.py",
    ),
    (
        "P5 runtime resolver trace context (GAP.5 partial)",
        ROOT / "apps" / "platform_runtime" / "tracing.py",
    ),
    ("P5 EVENT_DRIVEN_FLOWS", ROOT / "docs" / "EVENT_DRIVEN_FLOWS.md"),
    (
        "P6 Phase H URL tests",
        ROOT / "apps" / "accounts" / "tests" / "test_phase_h_ux_verification.py",
    ),
    ("P7 pre_deploy_gate", ROOT / "scripts" / "pre_deploy_gate.sh"),
    ("Interop trust doc", ROOT / "docs" / "INTEGRATION_PARTNER_TRUST_SIGNALS.md"),
    # §0.3.3 beyond-reach BR evidence (docs + regression tests)
    ("BR SLO doc", ROOT / "docs" / "SLO_TARGETS_AND_OBSERVABILITY.md"),
    ("N16 SOC2/ISO program", ROOT / "docs" / "N16_SOC2_ISO_EXECUTION_PROGRAM.md"),
    ("BR top-20 tasks", ROOT / "docs" / "TOP_20_LOW_CLICK_TASKS.md"),
    ("BR-03 PWA/offline", ROOT / "docs" / "MOBILE_PWA_OFFLINE_BR03.md"),
    (
        "BR-04 migration CSV diff runbook",
        ROOT / "docs" / "MIGRATION_CSV_DIFF_RUNBOOK.md",
    ),
    ("BR-05 live compliance", ROOT / "docs" / "LIVE_COMPLIANCE_VALIDATE_BR05.md"),
    (
        "BR-05 attendance packs",
        ROOT / "apps" / "compliance" / "attendance_region_packs.py",
    ),
    (
        "BR-05 enrollment packs",
        ROOT / "apps" / "compliance" / "enrollment_region_packs.py",
    ),
    ("BR-06 EWS", ROOT / "docs" / "EWS_V1_RUNMY.md"),
    (
        "BR-07/09 super tools test",
        ROOT / "apps" / "schools" / "tests" / "test_super_beyond_reach.py",
    ),
    ("BR-08 comms i18n", ROOT / "docs" / "COMMUNICATION_I18N_POLICY_BR08.md"),
    ("BR-09 Trojan legacy", ROOT / "docs" / "TROJAN_READ_ONLY_LEGACY_BR09.md"),
    ("BR-10 billing SKUs", ROOT / "docs" / "BILLING_SKUS_ENTITLEMENTS_BR10.md"),
    ("BR-12 mega-file plan", ROOT / "docs" / "MEGA_FILE_SPLIT_PLAN_BR12.md"),
    ("Template editing convention", ROOT / "docs" / "TEMPLATE_EDITING_CONVENTION.md"),
    ("BR-13 premium pass", ROOT / "docs" / "PREMIUM_UX_MANUAL_PASS_BR13.md"),
    ("BR audit checklist", ROOT / "docs" / "BR_BEYOND_REACH_AUDIT.md"),
    ("BR-08 comms_locale helper", ROOT / "apps" / "communication" / "comms_locale.py"),
    (
        "BR-08 thread retention cmd",
        ROOT
        / "apps"
        / "communication"
        / "management"
        / "commands"
        / "purge_thread_message_retention.py",
    ),
    (
        "BR-08 message locale wiring test",
        ROOT / "apps" / "communication" / "tests" / "test_message_locale_wiring.py",
    ),
    ("BR regression test runner", ROOT / "scripts" / "run_br_regression_tests.sh"),
    # Wave 25 / N17–N20 — marketplace impact graph + tenant pack install evidence (§0.1.5)
    (
        "N17 package dependency graph JS",
        ROOT / "static" / "js" / "package-dependency-graph.js",
    ),
    (
        "N20 tenant pack install service",
        ROOT / "apps" / "packages" / "tenant_pack_install.py",
    ),
    (
        "N17/N20 tenant package rollback view",
        ROOT / "apps" / "siteconfig" / "views_package_rollback.py",
    ),
    (
        "N17/N20 installed packages rollback template",
        ROOT / "templates" / "siteconfig" / "installed_packages_rollback.html",
    ),
    (
        "N20 tenant pack install tests",
        ROOT / "apps" / "packages" / "tests" / "test_tenant_pack_install.py",
    ),
    (
        "N20 DocumentPack/ExperiencePack version migration",
        ROOT
        / "apps"
        / "packages"
        / "migrations"
        / "0005_documentpack_experiencepack_version.py",
    ),
    ("N24 observability map", ROOT / "docs" / "N24_OBSERVABILITY_AND_ONCALL.md"),
    (
        "Wave 6 roll-call draft wiring test",
        ROOT / "apps" / "portal" / "tests" / "test_roll_call_draft_wiring.py",
    ),
    (
        "RESILIENT_EDGE critical-read JS",
        ROOT / "static" / "js" / "critical-read-degraded.js",
    ),
    (
        "RESILIENT_EDGE wiring test",
        ROOT / "apps" / "portal" / "tests" / "test_resilient_edge_wiring.py",
    ),
    (
        "POS fiscal migration",
        ROOT / "apps" / "schoolops" / "migrations" / "0011_possaleline_tax.py",
    ),
    (
        "Compliance erasure template wiring test",
        ROOT / "apps" / "compliance" / "tests" / "test_erasure_template_wiring.py",
    ),
    (
        "Finance form-draft template wiring test",
        ROOT / "apps" / "finance" / "tests" / "test_finance_form_draft_templates.py",
    ),
    (
        "Finance invoice PDF receipt wiring test",
        ROOT / "apps" / "finance" / "tests" / "test_invoice_receipt_pdf.py",
    ),
    (
        "N28 north-star upcoming deadlines API",
        ROOT / "apps" / "api" / "north_star_api_views.py",
    ),
    ("N22 RTL/regional UX doc", ROOT / "docs" / "N22_RTL_AND_REGIONAL_UX.md"),
    (
        "N22 region_settings RTL context test",
        ROOT / "apps" / "siteconfig" / "tests" / "test_n22_region_settings_rtl.py",
    ),
    (
        "BR-12 marketing page definitions split",
        ROOT / "apps" / "schools" / "marketing_page_definitions.py",
    ),
    ("BR-12 super_views constants", ROOT / "apps" / "schools" / "super_views_constants.py"),
    (
        "BR-12 command center data module",
        ROOT / "apps" / "schools" / "super_views_command_center_data.py",
    ),
    (
        "BR-12 command center data test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_command_center_data.py",
    ),
    (
        "BR-12 command center HTML views module",
        ROOT / "apps" / "schools" / "super_views_command_center_views.py",
    ),
    (
        "BR-12 command center HTML views re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_command_center_views.py",
    ),
    (
        "BR-12 overview surfaces module (schools list + analytics)",
        ROOT / "apps" / "schools" / "super_views_overview_surfaces.py",
    ),
    (
        "BR-12 overview surfaces re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_overview_surfaces.py",
    ),
    (
        "BR-12 super_views dashboard helpers module",
        ROOT / "apps" / "schools" / "super_views_dashboard_helpers.py",
    ),
    (
        "BR-12 super_views dashboard surfaces module",
        ROOT / "apps" / "schools" / "super_views_dashboard_surfaces.py",
    ),
    (
        "BR-12 super_views dashboard surfaces re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_dashboard_surfaces.py",
    ),
    (
        "BR-12 super_views exports module",
        ROOT / "apps" / "schools" / "super_views_exports.py",
    ),
    (
        "BR-12 super_views exports re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_exports.py",
    ),
    (
        "BR-12 super_views geo/plans API module",
        ROOT / "apps" / "schools" / "super_views_geo_api.py",
    ),
    (
        "BR-12 super_views geo API re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_geo_api.py",
    ),
    (
        "BR-12 super_views school lifecycle/policy API module",
        ROOT / "apps" / "schools" / "super_views_school_api.py",
    ),
    (
        "BR-12 super_views school API re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_school_api.py",
    ),
    (
        "BR-12 super_views policy diff module",
        ROOT / "apps" / "schools" / "super_views_policy.py",
    ),
    (
        "BR-12 super_views policy re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_policy.py",
    ),
    (
        "BR-12 super_views trust surface module",
        ROOT / "apps" / "schools" / "super_views_trust_surface.py",
    ),
    (
        "BR-12 super_views trust surface re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_trust_surface.py",
    ),
    (
        "BR-12 super_views support module",
        ROOT / "apps" / "schools" / "super_views_support.py",
    ),
    (
        "BR-12 super_views support re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_support.py",
    ),
    (
        "BR-12 super_views AI module",
        ROOT / "apps" / "schools" / "super_views_ai.py",
    ),
    (
        "BR-12 super_views AI re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_ai.py",
    ),
    (
        "BR-12 super_views impersonation module",
        ROOT / "apps" / "schools" / "super_views_impersonation.py",
    ),
    (
        "BR-12 super_views impersonation re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_impersonation.py",
    ),
    (
        "BR-12 super_views runtime ops module",
        ROOT / "apps" / "schools" / "super_views_runtime_ops.py",
    ),
    (
        "BR-12 super_views runtime ops re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_runtime_ops.py",
    ),
    (
        "BR-12 super_views platform monitoring module",
        ROOT / "apps" / "schools" / "super_views_platform_monitoring.py",
    ),
    (
        "BR-12 super_views platform monitoring re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_platform_monitoring.py",
    ),
    (
        "BR-12 super_views billing console module",
        ROOT / "apps" / "schools" / "super_views_billing_console.py",
    ),
    (
        "BR-12 super_views billing console re-export test",
        ROOT / "apps" / "schools" / "tests" / "test_super_views_billing_console.py",
    ),
    (
        "N23 inclusive terminology and imagery doc",
        ROOT / "docs" / "N23_INCLUSIVE_TERMINOLOGY_AND_IMAGERY.md",
    ),
    (
        "N3 payroll portal table header test",
        ROOT / "apps" / "payroll" / "tests" / "test_payroll_template_table_a11y.py",
    ),
    (
        "N3 misc table header templates (analytics/evals/reports)",
        ROOT / "apps" / "portal" / "tests" / "test_n3_misc_table_header_templates.py",
    ),
]


def main() -> int:
    missing = [(label, p) for label, p in REQUIRED if not p.is_file()]
    if missing:
        for label, p in missing:
            print(f"MISSING [{label}]: {p.relative_to(ROOT)}", file=sys.stderr)
        return 1
    print(f"verify_sot_pillar_evidence: OK ({len(REQUIRED)} paths)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
