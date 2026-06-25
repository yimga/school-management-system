#!/usr/bin/env python3
"""Verify provisioning → go-live program artifacts (batch 1731 + Pillar E 1732–1742)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    errors: list[str] = []
    handoff = ROOT / "docs/phase_checklists/PROVISIONING_TO_GOLIVE_AUDIT.md"
    if not handoff.is_file():
        errors.append("missing PROVISIONING_TO_GOLIVE_AUDIT.md")
    else:
        text = handoff.read_text(encoding="utf-8")
        if text.count("PGL-") < 40:
            errors.append("audit ledger fewer than 40 PGL findings")
        if "Golden path" not in text:
            errors.append("audit missing golden path section")

    required = [
        "apps/schools/school_readiness.py",
        "apps/schools/views_school_readiness.py",
        "apps/schools/offline_workflow_handlers.py",
        "apps/setup_studio/wizards/academic_year_setup.json",
        "var/design-previews/provisioning-journey-train-browsable.html",
        "var/design-previews/provisioning-golive-hub-browsable.html",
        "var/design-previews/provisioning-golive-lab-browsable.html",
        "var/design-previews/migration-branch-onboarding-browsable.html",
        "var/design-previews/launch-ceremony-browsable.html",
        "var/design-previews/tenant-dashboard-style-branding.html",
        "templates/partials/tenant/school_readiness_journey_train.html",
        "templates/partials/tenant/execute_launch_form.html",
        "templates/partials/tenant/launch_ceremony_banner.html",
        "templates/partials/tenant/setup_golive_pending_banner.html",
        "templates/partials/tenant/provisioning_partial_failure_banner.html",
        "templates/partials/tenant/setup_dashboard_style_strip.html",
        "apps/schools/management/commands/seed_provisioning_golive_e2e.py",
        "apps/schools/tests/test_provisioning_golive_e2e.py",
        "static/js/rmc-setup-surface-readiness.js",
        "static/js/rmc-school-readiness-cache.js",
        "static/js/rmc-journey-offline-mirror.js",
        "static/js/rmc-discipline-refer.js",
        "static/js/offline-db.js",
        "docs/phase_checklists/PILLAR_E_OFFLINE_CI_MATRIX.md",
        "var/design-previews/world-class-tenant-journey-hub-browsable.html",
        "var/design-previews/provisioning-offline-edge-lab-browsable.html",
    ]
    for rel in required:
        if not (ROOT / rel).is_file():
            errors.append(f"missing {rel}")

    services = (ROOT / "apps/setup_studio/services.py").read_text(encoding="utf-8")
    if "_academic_year_wizard_link" not in services:
        errors.append("services.py missing academic year wizard link helper")
    if "_account_migration_wizard_link" not in services:
        errors.append("services.py missing migration wizard link helper")
    if "needs_resume" not in (ROOT / "apps/schools/school_readiness.py").read_text(encoding="utf-8"):
        errors.append("school_readiness missing needs_resume provision field")
    if "has_launched" not in (ROOT / "apps/accounts/views.py").read_text(encoding="utf-8"):
        errors.append("views.py missing has_launched setup landing gate")

    tenant_urls = (ROOT / "config/tenant_urls.py").read_text(encoding="utf-8")
    if "api_school_readiness" not in tenant_urls:
        errors.append("tenant_urls missing api_school_readiness route")

    models_dash = (ROOT / "apps/siteconfig/models_dashboard.py").read_text(encoding="utf-8")
    if models_dash.count('"soft-glass"') < 1 or "family-friendly" not in models_dash:
        errors.append("models_dashboard missing 8-preset VISUAL_PRESET_CHOICES")

    views_py = (ROOT / "apps/accounts/views.py").read_text(encoding="utf-8")
    if "rmc_school_readiness" not in views_py or "has_launched" not in views_py:
        errors.append("backend_dashboard missing unified readiness context wiring")

    setup_partial = (ROOT / "templates/partials/tenant/setup_command_surface.html").read_text(
        encoding="utf-8"
    )
    if "school_readiness_journey_train" not in setup_partial:
        errors.append("setup_command_surface missing journey train partial")

    partial_fail = (
        ROOT / "templates/partials/tenant/provisioning_partial_failure_banner.html"
    ).read_text(encoding="utf-8")
    if 'data-page-critical-read="1"' not in partial_fail:
        errors.append("provisioning_partial_failure_banner missing data-page-critical-read")

    launch_strip = (ROOT / "templates/partials/tenant/launch_playbook_strip.html").read_text(
        encoding="utf-8"
    )
    if "launch_playbook_ack" not in launch_strip:
        errors.append("launch_playbook_strip missing offline ack workflow")

    offline_db = (ROOT / "static/js/offline-db.js").read_text(encoding="utf-8")
    if "school_readiness" not in offline_db or "discipline_incidents" not in offline_db:
        errors.append("offline-db.js missing journey Dexie stores")

    offline_apply = (ROOT / "apps/platform_runtime/offline_workflow_apply.py").read_text(
        encoding="utf-8"
    )
    if "apply_tenant_journey_workflow" not in offline_apply:
        errors.append("offline_workflow_apply missing tenant journey dispatch")

    if "quick_set_dashboard_visual_preset" not in (ROOT / "apps/siteconfig/urls.py").read_text(
        encoding="utf-8"
    ):
        errors.append("siteconfig urls missing quick_set_dashboard_visual_preset")

    if errors:
        for err in errors:
            print(f"FAIL: {err}")
        return 1
    print("PROVISIONING_GOLIVE_PROGRAM_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
