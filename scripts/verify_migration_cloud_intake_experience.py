#!/usr/bin/env python3
"""Gate: Migration Cloud intake/upload experience is operator-grade.

This verifier is intentionally narrow. It checks that the upload/start flow
exposes the command-center UI, drag/drop upload surface, source-family cards,
control totals, safety rails, and the backend persistence that makes those
rails real on the created bundle.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIGRATION_CLOUD_UI = "static/css/migration-cloud-ui.css"


def _contains(path: str, token: str) -> bool:
    return token in (ROOT / path).read_text(encoding="utf-8")


def main() -> int:
    checks = [
        (
            "intake_command_center",
            _contains("templates/migration_cloud/intake_new.html", "data-mc-intake-command-center"),
            "template exposes the intake command-center header",
        ),
        (
            "intake_premium_v2_layer",
            _contains("templates/migration_cloud/intake_new.html", "rmc-intake-v2")
            and _contains("templates/migration_cloud/intake_new.html", "migration-cloud-intake-premium.css")
            and _contains("templates/migration_cloud/intake_new.html", "data-mc-readiness-card")
            and _contains("static/css/migration-cloud-intake-premium.css", ".rmc-intake-stepper__fill"),
            "intake v2 premium workbench CSS and live readiness sidecar are wired",
        ),
        (
            "method_family_cards",
            _contains("templates/migration_cloud/intake_new.html", "data-mc-method-card"),
            "template exposes upload/url/live-source method cards",
        ),
        (
            "drag_drop_upload_zone",
            _contains("templates/migration_cloud/intake_new.html", "data-mc-upload-dropzone")
            and _contains("static/js/migration-cloud-intake.js", "data-mc-upload-dropzone"),
            "drag/drop upload zone and JS binding exist",
        ),
        (
            "control_totals_fields",
            all(
                _contains("templates/migration_cloud/intake_new.html", token)
                for token in (
                    'name="expected_students_count"',
                    'name="expected_guardians_count"',
                    'name="expected_invoice_count"',
                    'name="expected_invoice_total_amount"',
                )
            ),
            "operator can enter row and finance control totals at intake",
        ),
        (
            "safety_rail_fields",
            all(
                _contains("templates/migration_cloud/intake_new.html", token)
                for token in (
                    'name="diff_mode"',
                    'name="diff_since"',
                    'name="apply_atomic"',
                    'name="parity_drift_rollback_pct"',
                )
            ),
            "operator can set diff mode, atomic apply, and rollback threshold at intake",
        ),
        (
            "backend_persistence",
            all(
                _contains("apps/migration_cloud/views.py", token)
                for token in (
                    "def _clean_intake_options",
                    "expected_totals",
                    "diff_mode",
                    "apply_atomic",
                    "parity_drift_rollback_pct",
                    "def _apply_intake_options",
                )
            ),
            "view validates and persists intake guardrails onto MigrationBundle",
        ),
        (
            "focused_tests",
            all(
                _contains("apps/migration_cloud/tests/test_intake_view.py", token)
                for token in (
                    "test_upload_stores_control_totals_and_safety_rails",
                    "test_invalid_control_total_rejected",
                    "data-mc-upload-dropzone",
                )
            ),
            "focused Django tests lock the new experience and backend contract",
        ),
        (
            "migration_cloud_ui_repair_layer",
            _contains("templates/control_plane_skeleton.html", "css/migration-cloud-ui.css")
            and _contains("templates/portal_base.html", "css/migration-cloud-ui.css")
            and _contains(MIGRATION_CLOUD_UI, ".rmc-page--migration-cloud-intake")
            and _contains(MIGRATION_CLOUD_UI, "overflow: visible"),
            "Migration Cloud has a late-loading scoped UI layer on manager and portal shells",
        ),
        (
            "source_identification_panel_not_clipped",
            _contains("templates/migration_cloud/intake_new.html", "data-mc-source-identify-panel")
            and _contains(MIGRATION_CLOUD_UI, ".rmc-intake-panel--source-id")
            and _contains(MIGRATION_CLOUD_UI, "details > summary"),
            "source screenshot/PDF identification is a full intake panel and details summaries cannot clip text",
        ),
        (
            "customer_guardian_surfaces_scoped",
            all(
                _contains(path, "data-rmc-migration-cloud-surface")
                for path in (
                    "templates/migration_cloud/customer/intake_start.html",
                    "templates/migration_cloud/customer/intake_list.html",
                    "templates/migration_cloud/customer/intake_status.html",
                    "templates/migration_cloud/customer/intake_sign_maa.html",
                    "templates/migration_cloud/customer/intake_abandon_confirm.html",
                    "templates/migration_cloud/customer/consent_campaign_start.html",
                    "templates/migration_cloud/customer/consent_campaign_status.html",
                    "templates/migration_cloud/guardian_consent/consent_landing.html",
                    "templates/migration_cloud/guardian_consent/consent_completed.html",
                )
            ),
            "customer and guardian Migration Cloud pages are opted into the repair layer",
        ),
        (
            "service_worker_caches_ui_repair",
            _contains("static/js/service-worker.js", 'CACHE_VERSION = "sms-v')
            and _contains("static/js/service-worker.js", "/static/css/migration-cloud-ui.css"),
            "service worker cache version and static asset list include the UI repair CSS",
        ),
    ]

    failed = [row for row in checks if not row[1]]
    if failed:
        print("verify_migration_cloud_intake_experience: FAIL", file=sys.stderr)
        for name, _ok, proof in failed:
            print(f"  FAIL {name}: {proof}", file=sys.stderr)
        return 1

    print(f"verify_migration_cloud_intake_experience: PASS ({len(checks)}/{len(checks)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
