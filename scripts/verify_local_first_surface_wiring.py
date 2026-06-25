#!/usr/bin/env python3
"""Verify local-first field_capture wiring on P0 schoolops/finance/people templates."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

REQUIRED_MARKERS = (
    "templates/schoolops/substitute_handover_form.html",
    "templates/schoolops/lost_belongings_mint.html",
    "templates/schoolops/lost_belongings_recover.html",
    "templates/schoolops/ops_pos.html",
    "templates/finance/cash_office_closure.html",
    "templates/finance/generate_fees.html",
    "templates/finance/scan_teller_placeholder.html",
    "templates/finance/split_allocation.html",
    "templates/finance/suspense_queue.html",
    "templates/finance/access_bulk.html",
    "templates/finance/reports.html",
    "templates/finance/permission_to_pay.html",
    "templates/compliance/erasure_request.html",
    "templates/requests/detail.html",
    "templates/people/backend_student_create.html",
    "templates/people/backend_applicant_create.html",
    "templates/partials/tenant/launch_playbook_strip.html",
    "templates/partials/tenant/academic_year_close_checklist.html",
    "templates/teacher/disciplinary.html",
)

PORTAL_OFFLINE_WIRING = (
    "partials/rmc_sms_offline_config.html",
    "rmc-offline-portal-forms.js",
)


def main() -> int:
    findings: list[str] = []

    portal = (ROOT / "templates/portal_base.html").read_text(encoding="utf-8", errors="replace")
    for needle in PORTAL_OFFLINE_WIRING:
        if needle not in portal:
            findings.append(f"portal_base.html missing {needle}")

    psc = (ROOT / "apps/siteconfig/platform_surface_config.py").read_text(
        encoding="utf-8", errors="replace"
    )
    if "deltaEndpointUrl" not in psc or "hydrateEndpoints" not in psc:
        findings.append("platform_surface_config missing deltaEndpointUrl/hydrateEndpoints")

    js = (ROOT / "static/js/rmc-offline-portal-forms.js").read_text(encoding="utf-8", errors="replace")
    if "function wireFieldCapture" not in js:
        findings.append("rmc-offline-portal-forms.js missing wireFieldCapture")

    for rel in REQUIRED_MARKERS:
        path = ROOT / rel
        if not path.is_file():
            findings.append(f"missing template {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if 'data-rmc-offline-form="field_capture"' not in text:
            findings.append(f"{rel} missing field_capture marker")

    ctx = (ROOT / "apps/siteconfig/context_processors.py").read_text(encoding="utf-8", errors="replace")
    if "OFFLINE_DELTA_URL" not in ctx:
        findings.append("context_processors missing OFFLINE_DELTA_URL")

    if findings:
        print("verify_local_first_surface_wiring: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print(
        "verify_local_first_surface_wiring: LOCAL_FIRST_SURFACE_WIRING_PASS "
        f"templates={len(REQUIRED_MARKERS)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
