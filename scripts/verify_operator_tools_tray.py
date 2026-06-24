#!/usr/bin/env python3
"""Verify Operator + Tenant Tools edge-tray wiring on platform shells."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    failures: list[str] = []

    skeleton = _read("templates/control_plane_skeleton.html")
    admin_site = _read("templates/admin/base_site.html")
    portal = _read("templates/portal_base.html")
    operator_scripts = _read("templates/partials/rmc_operator_tools_scripts.html")
    operator_styles = _read("templates/partials/rmc_operator_tools_styles.html")
    tenant_scripts = _read("templates/partials/rmc_tenant_tools_scripts.html")
    tenant_styles = _read("templates/partials/rmc_tenant_tools_styles.html")

    for needle in (
        "rmc_operator_tools_styles.html",
        "rmc_operator_tools_scripts.html",
    ):
        if needle not in skeleton:
            failures.append(f"control_plane_skeleton.html missing {needle}")

    for needle in (
        "rmc_operator_tools_styles.html",
        "rmc_operator_tools_scripts.html",
    ):
        if needle not in admin_site:
            failures.append(f"admin/base_site.html missing {needle}")

    for needle in (
        "rmc_tenant_tools_styles.html",
        "rmc_tenant_tools_scripts.html",
    ):
        if needle not in portal:
            failures.append(f"portal_base.html missing {needle}")

    for needle in (
        "rmc_operator_tools_styles.html",
        "rmc_operator_tools_scripts.html",
    ):
        if needle not in portal:
            failures.append(f"portal_base.html missing manager bridge {needle}")

    if "page-data-rmc-operator-tools" in portal:
        failures.append("portal_base.html must not inline operator tools page data")

    if "page-data-rmc-tenant-tools" in portal:
        failures.append("portal_base.html must include tenant tools via partial only")

    if "request.public_host_kind == 'manager'" not in operator_scripts:
        failures.append("rmc_operator_tools_scripts.html missing manager host gate")

    if "cockpit.operator_tools.enabled" not in operator_scripts:
        failures.append("rmc_operator_tools_scripts.html missing operator_tools cockpit gate")
    if "cockpit.operator_tools.enabled" not in operator_styles:
        failures.append("rmc_operator_tools_styles.html missing operator_tools cockpit gate")

    if "request.public_host_kind != 'manager'" not in tenant_scripts:
        failures.append("rmc_tenant_tools_scripts.html missing tenant host gate")

    if "cockpit.tenant_tools.enabled" not in tenant_scripts:
        failures.append("rmc_tenant_tools_scripts.html missing tenant_tools cockpit gate")

    if 'data-rmc-back-to-top-policy="always"' in skeleton:
        failures.append("control_plane_skeleton still uses always-on back-to-top policy")

    if (
        'data-rmc-back-to-top-policy="always"'
        in portal
        and "cockpit.tenant_tools.enabled" not in portal
    ):
        failures.append("portal_base still uses unconditional always-on back-to-top policy")

    operator_slots = _read("apps/assist_dock/operator_tools_slots.py")
    if "operator-notebook" not in operator_slots:
        failures.append("operator_tools_slots.py missing operator-notebook registration")

    tenant_slots = _read("apps/assist_dock/tenant_tools_slots.py")
    for slot_id in ("tenant-kb", "tenant-support", "tenant-command"):
        if slot_id not in tenant_slots:
            failures.append(f"tenant_tools_slots.py missing {slot_id} registration")

    js = _read("static/js/rmc-operator-tools-tray.js")
    css = _read("static/css/rmc-operator-tools-tray.css")
    if "data-rmc-assist-layout" not in js or "edge-tray" not in js:
        failures.append("rmc-operator-tools-tray.js missing edge-tray transform")
    if "page-data-rmc-tenant-tools" not in js:
        failures.append("rmc-operator-tools-tray.js missing tenant tools config island")
    if "admin-manager-shell" not in js:
        failures.append("rmc-operator-tools-tray.js missing admin-manager-shell surface gate")
    if "isAuthLanding" not in js:
        failures.append("rmc-operator-tools-tray.js missing auth landing guard")
    if "syncTrayEmptyState" not in js:
        failures.append("rmc-operator-tools-tray.js missing syncTrayEmptyState")
    if "registrySlotHref" not in js:
        failures.append("rmc-operator-tools-tray.js missing registrySlotHref tenant URL resolver")
    if "data-rmc-tools-tray-empty" not in js:
        failures.append("rmc-operator-tools-tray.js missing tray empty state marker")
    if "data-rmc-tools-sections-empty" not in js:
        failures.append("rmc-operator-tools-tray.js missing sections panel empty state")
    if ".rmc-operator-tools__tray-empty" not in css:
        failures.append("rmc-operator-tools-tray.css missing tray empty state styles")

    if ".rmc-operator-tools__edge-tab" not in css:
        failures.append("rmc-operator-tools-tray.css missing edge tab styles")
    if 'body[data-rmc-workspace-tools="tenant"]' not in css:
        failures.append("rmc-operator-tools-tray.css missing tenant workspace selector")

    manager_cockpit = _read("apps/siteconfig/cockpit_manager_200x.py")
    if "operator_tools" not in manager_cockpit:
        failures.append("cockpit_manager_200x.py missing operator_tools defaults")

    tenant_cockpit = _read("apps/siteconfig/cockpit_tenant_tools.py")
    if "tenant_tools_defaults" not in tenant_cockpit:
        failures.append("cockpit_tenant_tools.py missing tenant_tools_defaults")

    cockpit_ctx = _read("apps/siteconfig/cockpit_context.py")
    if 'tenant_cockpit["tenant_tools"]' not in cockpit_ctx:
        failures.append("cockpit_context.py missing tenant_tools wiring")

    if "rmc_tools_tray_context_stack.html" not in operator_scripts:
        failures.append("rmc_operator_tools_scripts.html missing tools tray context stack")
    if "rmc_tools_tray_context_stack.html" not in tenant_scripts:
        failures.append("rmc_tenant_tools_scripts.html missing tools tray context stack")
    if "mountContextStack" not in js:
        failures.append("rmc-operator-tools-tray.js missing mountContextStack")
    for needle in (
        "applyPageContext",
        "resolvePagePlan",
        "renderPageHead",
        "renderPageQuickActions",
    ):
        if needle not in js:
            failures.append(f"rmc-operator-tools-tray.js missing {needle}")
    if ".rmc-operator-tools__context-stack" not in css:
        failures.append("rmc-operator-tools-tray.css missing context-stack styles")
    if ".rmc-operator-tools__page-head" not in css:
        failures.append("rmc-operator-tools-tray.css missing page-head styles")

    page_ctx = ROOT / "apps/assist_dock/tools_tray_page_context.py"
    if not page_ctx.is_file():
        failures.append("apps/assist_dock/tools_tray_page_context.py missing")
    elif "build_tools_tray_page_payload" not in page_ctx.read_text(encoding="utf-8"):
        failures.append("tools_tray_page_context.py missing build_tools_tray_page_payload")

    operator_page_data = _read("templates/partials/rmc_operator_tools_page_data.html")
    tenant_page_data = _read("templates/partials/rmc_tenant_tools_page_data.html")
    if '"page":' not in operator_page_data or "TOOLS_TRAY_PAGE_JSON" not in operator_page_data:
        failures.append("rmc_operator_tools_page_data.html missing page-aware TOOLS_TRAY_PAGE_JSON")
    if '"page":' not in tenant_page_data or "TOOLS_TRAY_PAGE_JSON" not in tenant_page_data:
        failures.append("rmc_tenant_tools_page_data.html missing page-aware TOOLS_TRAY_PAGE_JSON")

    ctx_proc = _read("apps/assist_dock/context_processors.py")
    if "TOOLS_TRAY_PAGE_JSON" not in ctx_proc:
        failures.append("context_processors.py missing TOOLS_TRAY_PAGE_JSON export")
    dock_views = _read("apps/assist_dock/views.py")
    if '"tools_tray"' not in dock_views:
        failures.append("assist_dock/views.py missing tools_tray in context API")

    admin_site_tpl = _read("templates/admin/base_site.html")
    if "rmc_tenant_tools_scripts.html" not in admin_site_tpl:
        failures.append("admin/base_site.html missing tenant tools tray for tenant /admin/")
    if "[data-rmc-tools-tray-context]" not in js:
        failures.append("rmc-operator-tools-tray.js missing universal tray context gate")

    assist_js = _read("static/js/rmc-assist-dock.js")
    if "dispatchAssistDockContext" not in assist_js:
        failures.append("rmc-assist-dock.js missing dispatchAssistDockContext")
    if "tools_tray" not in assist_js or "rmc-tools-tray-page-sync" not in assist_js:
        failures.append("rmc-assist-dock.js missing tools_tray page-sync bridge")

    default_qa = ROOT / "apps/assist_dock/default_quick_actions.py"
    if not default_qa.is_file():
        failures.append("apps/assist_dock/default_quick_actions.py missing")
    elif "register_default_quick_actions" not in default_qa.read_text(encoding="utf-8"):
        failures.append("default_quick_actions.py missing register_default_quick_actions")

    apps_py = _read("apps/assist_dock/apps.py")
    if "register_default_quick_actions" not in apps_py:
        failures.append("assist_dock/apps.py must load default quick actions")

    tray_stack = _read("templates/partials/rmc_tools_tray_context_stack.html")
    if "data-rmc-wfp-tray-slot" not in tray_stack:
        failures.append("rmc_tools_tray_context_stack.html missing workflow chip tray slot")
    topbar = _read("templates/partials/manager_operator_topbar.html")
    if "rmc_workflow_progress_strip.html" in topbar:
        failures.append("manager_operator_topbar.html must not include workflow progress strip")

    smoke = _read("scripts/smoke_operator_tools_tray.py")
    if "OPERATOR_TOOLS_SMOKE_PASS" not in smoke:
        failures.append("smoke_operator_tools_tray.py missing OPERATOR_TOOLS_SMOKE_PASS marker")
    if "_assert_tenant_tray" not in smoke:
        failures.append("smoke_operator_tools_tray.py missing tenant tray assertion")
    if "_bootstrap_qa" not in smoke:
        failures.append("smoke_operator_tools_tray.py missing QA bootstrap helper")
    if "_login_surface" not in smoke:
        failures.append("smoke_operator_tools_tray.py missing shared login helper")

    platform_cov = ROOT / "scripts/verify_tools_tray_platform_coverage.py"
    if platform_cov.is_file():
        import subprocess

        proc = subprocess.run(
            [sys.executable, str(platform_cov)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            failures.append("verify_tools_tray_platform_coverage.py failed")
            if proc.stderr:
                failures.append(proc.stderr.strip().splitlines()[-1])

    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        return 1

    print("OK: operator + tenant tools edge-tray contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
