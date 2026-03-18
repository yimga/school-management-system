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
    ("P5 EVENT_DRIVEN_FLOWS", ROOT / "docs" / "EVENT_DRIVEN_FLOWS.md"),
    (
        "P6 Phase H URL tests",
        ROOT / "apps" / "accounts" / "tests" / "test_phase_h_ux_verification.py",
    ),
    ("P7 pre_deploy_gate", ROOT / "scripts" / "pre_deploy_gate.sh"),
    ("Interop trust doc", ROOT / "docs" / "INTEGRATION_PARTNER_TRUST_SIGNALS.md"),
    # §0.3.3 beyond-reach BR evidence (docs + regression tests)
    ("BR SLO doc", ROOT / "docs" / "SLO_TARGETS_AND_OBSERVABILITY.md"),
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
