#!/usr/bin/env python3
"""Verifier: tenant offboarding surface (operator + tenant self-service + scheduler + admin)."""

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

    template = _text("templates/schools/super_tenant_360.html")
    for needle in (
        "Offboarding & data custody",
        "data-rmc-confirm-slug",
        "Permanent delete tenant",
        "Offboarding queue",
    ):
        if needle not in template:
            findings.append(f"super_tenant_360 missing: {needle}")

    tenant_tpl = _text("templates/siteconfig/tenant_self_offboarding.html")
    if "Close school account" not in tenant_tpl:
        findings.append("tenant_self_offboarding template missing")
    if "data-rmc-tenant-request-closure" not in tenant_tpl:
        findings.append("tenant self-service closure control missing")

    queue_tpl = _text("templates/schools/super_offboarding_queue.html")
    if "Offboarding queue" not in queue_tpl:
        findings.append("super_offboarding_queue template missing")

    admin_tpl = _text("templates/admin/schools/school/delete_guided.html")
    if "offboarding workflow" not in admin_tpl:
        findings.append("admin delete_guided template missing")

    admin_py = _text("apps/schools/admin.py")
    if "has_delete_permission" not in admin_py or "return False" not in admin_py:
        findings.append("SchoolAdmin delete guard missing")

    for js_path in (
        "static/js/_pages/schools__tenant_offboarding-1.js",
        "static/js/_pages/tenant_self_offboarding-1.js",
        "static/js/_pages/schools__super_offboarding_queue-1.js",
    ):
        js = _text(js_path)
        if not js:
            findings.append(f"missing {js_path}")
        elif "fetch(undefined)" in js:
            findings.append(f"{js_path} contains fetch(undefined)")

    urls = _text("apps/schools/super_urls.py")
    for name in (
        "api_school_offboarding",
        "api_school_offboarding_export",
        "api_school_offboarding_deactivate",
        "api_school_offboarding_purge",
        "api_school_offboarding_dual_approve",
        "api_school_offboarding_schedule",
        "api_school_offboarding_export_download",
        "offboarding_queue",
        "api_run_scheduled_purges",
    ):
        if f'name="{name}"' not in urls:
            findings.append(f"super_urls missing {name}")

    tenant_urls = _text("config/tenant_urls.py")
    for name in (
        "tenant_offboarding",
        "tenant_offboarding_export",
        "tenant_offboarding_request",
    ):
        if f'name="{name}"' not in tenant_urls:
            findings.append(f"tenant_urls missing {name}")

    purge_cmd = _text("apps/compliance/management/commands/tenant_purge.py")
    if "apply_purge" not in purge_cmd:
        findings.append("tenant_purge does not delegate to service")

    sched_cmd = REPO / "apps/compliance/management/commands/tenant_offboarding_run_scheduled_purges.py"
    if not sched_cmd.is_file():
        findings.append("missing tenant_offboarding_run_scheduled_purges command")

    if not (REPO / "apps/compliance/tenant_offboarding_storage.py").is_file():
        findings.append("missing tenant_offboarding_storage.py")

    if not (REPO / "apps/schools/tenant_offboarding_policy.py").is_file():
        findings.append("missing tenant_offboarding_policy.py")

    if not (REPO / "apps/schools/tenant_offboarding_notifications.py").is_file():
        findings.append("missing tenant_offboarding_notifications.py")

    tpl360 = _text("templates/schools/super_tenant_360.html")
    if "data-rmc-dual-approval-panel" not in tpl360:
        findings.append("super_tenant_360 missing dual approval panel")

    offboarding_js = _text("static/js/_pages/schools__tenant_offboarding-1.js")
    if "dualApprovedForPurge" not in offboarding_js:
        findings.append("schools__tenant_offboarding-1.js missing dual approval wiring")

    service = _text("apps/schools/tenant_offboarding.py")
    for sym in (
        "request_self_service_closure",
        "run_scheduled_purges",
        "schools_scheduled_for_purge",
    ):
        if sym not in service:
            findings.append(f"tenant_offboarding missing {sym}")

    tasks = _text("apps/schools/tasks.py")
    if "run_scheduled_tenant_purges" not in tasks:
        findings.append("Celery task run_scheduled_tenant_purges missing")

    settings = _text("config/settings.py")
    if "schools-run-scheduled-tenant-purges" not in settings:
        findings.append("CELERY_BEAT schools-run-scheduled-tenant-purges not wired")

    nav = _text("apps/schools/control_plane_nav.py")
    if 'name="super:offboarding_queue"' not in nav.replace("'", '"'):
        if "super:offboarding_queue" not in nav:
            findings.append("control_plane_nav missing offboarding_queue")

    studio = _text("templates/siteconfig/tenant_studio_hub.html")
    if "Close school account" not in studio:
        findings.append("tenant_studio_hub missing self-service offboarding link")

    schools_list = _text("templates/schools/super_schools_list.html")
    if "Offboarding queue" not in schools_list:
        findings.append("super_schools_list missing offboarding queue link")

    mig = REPO / "apps/schools/migrations/0053_schoolprovisioningevent_offboarding_extended.py"
    if not mig.is_file():
        findings.append("missing migration 0053")

    models = _text("apps/schools/models.py")
    for evt in (
        "OFFBOARDING_SELF_SERVICE_REQUESTED",
        "OFFBOARDING_AUTO_PURGE_EXECUTED",
    ):
        if evt not in models:
            findings.append(f"SchoolProvisioningEvent missing {evt}")

    if findings:
        print("FAIL: tenant offboarding surface")
        for item in findings:
            print(f"  - {item}")
        return 1

    print("PASS: tenant offboarding surface (extended)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
