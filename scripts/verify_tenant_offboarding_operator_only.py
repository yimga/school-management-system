#!/usr/bin/env python3
"""Verifier: operator-only offboarding defaults and wiring."""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parent.parent


def _text(rel: str) -> str:
    path = REPO / rel
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def main() -> int:
    findings: list[str] = []

    policy = _text("apps/schools/tenant_offboarding_policy.py")
    if 'TENANT_SELF_SERVICE_OFFBOARDING_ENABLED", "0"' not in policy:
        findings.append("self_service default must be 0 (operator-only)")
    if "def operator_only_offboarding" not in policy:
        findings.append("operator_only_offboarding() missing")

    service = _text("apps/schools/tenant_offboarding.py")
    for sym in (
        "request_tenant_offboarding",
        "approve_offboarding_request",
        "reject_offboarding_request",
        "operator_approval_required",
    ):
        if sym not in service:
            findings.append(f"tenant_offboarding missing {sym}")

    views = _text("apps/schools/views_tenant_self_offboarding.py")
    if "request_tenant_offboarding" not in views:
        findings.append("tenant view must call request_tenant_offboarding")

    dsar = _text("apps/lifecycle/views_dsar.py")
    if "operator_only_offboarding" not in dsar:
        findings.append("DSAR view must respect operator-only mode")
    if "mark_deleted" in dsar and "if operator_only" not in dsar:
        findings.append("DSAR must not always mark_deleted")

    urls = _text("apps/schools/super_urls.py")
    for name in (
        "api_school_offboarding_approve_request",
        "api_school_offboarding_reject_request",
        "api_school_offboarding_purge_certificate",
    ):
        if f'name="{name}"' not in urls:
            findings.append(f"super_urls missing {name}")

    tpl = _text("templates/siteconfig/tenant_self_offboarding.html")
    if "operator_only" not in tpl and "self_service.operator_only" not in tpl:
        findings.append("tenant template missing operator-only copy")

    queue = _text("templates/schools/super_offboarding_queue.html")
    if "data-rmc-approve-request" not in queue:
        findings.append("offboarding queue missing approve control")

    render_yaml = _text("render.yaml")
    if "TENANT_SELF_SERVICE_OFFBOARDING_ENABLED" in render_yaml:
        idx = render_yaml.find("TENANT_SELF_SERVICE_OFFBOARDING_ENABLED")
        chunk = render_yaml[idx : idx + 120]
        if 'value: "0"' not in chunk and "value: '0'" not in chunk:
            findings.append("render.yaml should set TENANT_SELF_SERVICE_OFFBOARDING_ENABLED=0")

    for rel in (
        "apps/schools/offboarding_switching_pack.py",
        "apps/schools/offboarding_integrations.py",
    ):
        if not (REPO / rel).is_file():
            findings.append(f"missing {rel}")

    if "operator_approval_required" not in service:
        findings.append("tenant_offboarding missing operator_approval_required gate")

    public = _text("apps/schools/views_offboarding_public.py")
    if "verify_deletion_certificate" not in public:
        findings.append("missing public certificate verify view")

    api_urls = _text("apps/api/urls.py")
    if "offboarding-verify-deletion-certificate" not in api_urls:
        findings.append("api urls missing certificate verify route")

    tpl = _text("templates/siteconfig/tenant_lifecycle_command_center.html")
    if "data-rmc-offboarding-exit-status" not in tpl:
        findings.append("lifecycle command center missing exit status panel")

    parent_tpl = _text("templates/portal/parent_data_rights.html")
    if "parent_data_rights" not in parent_tpl and "data rights" not in parent_tpl.lower():
        findings.append("parent data rights template missing")

    portal_urls = _text("apps/portal/urls.py")
    if "parent_data_rights" not in portal_urls:
        findings.append("portal urls missing parent_data_rights")

    if not (REPO / "config/marketing_content/offboarding-sla.json").is_file():
        findings.append("missing marketing offboarding-sla.json")

    main_urls = _text("config/urls.py")
    if "marketing_trust_offboarding_sla" not in main_urls:
        findings.append("config urls missing marketing_trust_offboarding_sla")

    if findings:
        print("FAIL: tenant offboarding operator-only")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("PASS: tenant offboarding operator-only")
    return 0


if __name__ == "__main__":
    sys.exit(main())
