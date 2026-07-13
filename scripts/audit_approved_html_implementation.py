#!/usr/bin/env python3
"""Audit that approved design-preview HTML contracts reached live source files.

This is intentionally file-backed. The approved previews are design contracts;
this audit verifies the selectors, links, and safety boundaries that make those
contracts render in Django admin, tenant command pages, palette preview, tenant
blueprints, migration preview, and the assist/help relocation.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECTS_ROOT = ROOT.parent
WORKSPACE_ROOT = PROJECTS_ROOT.parent


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def _has(rel: str, needle: str, failures: list[str]) -> None:
    path = ROOT / rel
    if not path.is_file():
        failures.append(f"missing file: {rel}")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if needle not in text:
        failures.append(f"{rel}: missing `{needle}`")


def _abs_has(path: Path, needle: str, failures: list[str]) -> None:
    if not path.is_file():
        failures.append(f"missing approved preview: {path}")
        return
    text = path.read_text(encoding="utf-8", errors="replace")
    if needle not in text:
        failures.append(f"{path}: preview missing `{needle}`")


def main() -> int:
    failures: list[str] = []

    approved_previews = (
        (
            PROJECTS_ROOT / "school-management-system" / "var" / "design-previews" / "django-admin-canvas-intelligent-revamp.html",
            "Django admin, reworked as a full-canvas command surface",
        ),
        (
            WORKSPACE_ROOT / "_RMC_FIX_REVIEW_2026-07-02" / "index.html",
            "Fix Review Packet",
        ),
        (
            ROOT / "var" / "design-previews" / "tenant-option-a-palette-lifecycle-blueprint-audit.html",
            "Warm command workspace",
        ),
    )
    for path, token in approved_previews:
        _abs_has(path, token, failures)

    # Django admin canvas: operator and tenant /admin/ must share the canvas-first
    # contract and load the CSS that removes narrow form/table caps.
    for rel, token in (
        ("templates/admin/base_site.html", "rmc-admin-django-canvas-contract.css"),
        ("templates/admin/base.html", 'data-rmc-admin-canvas-contract="intelligent-full-width"'),
        ("templates/admin/base.html", 'data-rmc-admin-canvas-host="{% if is_manager_host %}operator{% else %}tenant{% endif %}"'),
        ("templates/admin/base.html", 'data-rmc-admin-content="canvas-first"'),
        ("templates/admin/change_form.html", 'data-rmc-admin-surface="smart-form"'),
        ("templates/admin/change_form.html", 'data-rmc-django-workspace="change-form"'),
        ("templates/admin/change_list.html", 'data-rmc-admin-surface="smart-changelist"'),
        ("templates/admin/change_list.html", 'data-rmc-admin-table-contract="native-table-scroll"'),
        ("static/css/rmc-admin-django-canvas-contract.css", "[data-rmc-admin-canvas-contract=\"intelligent-full-width\"]"),
        ("static/css/rmc-admin-django-canvas-contract.css", "[data-rmc-shell-root=\"django-admin\"]"),
    ):
        _has(rel, token, failures)

    # July fix-review packet: help is moved into sidebar/tooling, migration
    # preview is rendered as an in-page preview panel, and admin sites are split.
    for rel, token in (
        ("static/js/rmc-assist-dock.js", "[data-rmc-sidebar-page-help]"),
        ("templates/components/rmc_operator_workspace_dropdown.html", "More"),
        ("static/js/migration_cloud_wizard.js", "data-mc-preview-trigger"),
        ("static/js/migration_cloud_wizard.js", "mc-apply-preview"),
        ("config/admin.py", "tenant_admin_site = TenantAdminSite"),
        ("config/admin.py", "platform_admin_site = PlatformAdminSite"),
        ("config/tenant_urls.py", 'path("admin/", tenant_admin_site.urls)'),
        ("config/manager_urls.py", 'path("admin/", platform_admin_site.urls)'),
        ("templates/auth/tenant_admin_login.html", "tenant-admin-login"),
    ):
        _has(rel, token, failures)

    # Tenant Option A: sparse tenant pages must use the warm command workspace,
    # bounded work zones, tenant-local blueprint actions, and full palette preview.
    for rel, token in (
        ("templates/siteconfig/get_blueprints.html", "tenant-command-workspace.css"),
        ("templates/siteconfig/partials/get_blueprints_body.html", 'data-rmc-command-workspace="tenant-blueprints"'),
        ("templates/siteconfig/partials/get_blueprints_body.html", "Tenant-safe blueprints"),
        ("templates/siteconfig/partials/get_blueprints_body.html", "data-rmc-blueprint-preview-action"),
        ("templates/siteconfig/partials/get_blueprints_body.html", "data-rmc-blueprint-apply-action"),
        ("templates/siteconfig/partials/get_blueprints_body.html", "tenant_blueprint_setup_base_url"),
        ("templates/siteconfig/partials/get_blueprints_body.html", 'data-rmc-bounded-work-zone="tenant-blueprint-catalog"'),
        ("templates/platform_runtime/tenant_blueprint_setup.html", "world_class_guided_stepper.html"),
        ("templates/platform_runtime/tenant_blueprint_setup.html", "Apply tenant blueprint"),
        ("templates/platform_runtime/tenant_blueprint_setup.html", "Approval requested when risk requires it"),
        ("apps/platform_runtime/blueprint_contract.py", "tenant_safe_only"),
        ("apps/platform_runtime/blueprint_preview.py", "pack_not_found"),
        ("templates/admin/components/theme_preview_section.html", "preview-hero"),
        ("templates/admin/components/theme_preview_section.html", "preview-status-table"),
        ("templates/admin/components/theme_preview_section.html", "preview-form"),
        ("templates/admin/components/theme_preview_section.html", "Role dashboard"),
        ("static/css/site-settings-preview.css", ".preview-hero"),
        ("static/css/site-settings-preview.css", ".preview-status-table"),
        ("static/css/site-settings-preview.css", ".preview-form"),
        ("static/css/tenant-command-workspace.css", "[data-rmc-command-workspace]"),
        ("static/css/rmc-tenant-surface-scroll-contract.css", "[data-rmc-bounded-work-zone]"),
    ):
        _has(rel, token, failures)

    tenant_blueprint_body = _read("templates/siteconfig/partials/get_blueprints_body.html")
    if "manager_blueprints_url" in tenant_blueprint_body:
        failures.append("tenant blueprint body still renders manager_blueprints_url")
    if "/super/" in tenant_blueprint_body or "/configuration/blueprints/" in tenant_blueprint_body:
        failures.append("tenant blueprint body exposes operator blueprint paths")

    # The Claude artifact URL is private/non-fetchable from this environment. The
    # local tenant Option A preview is the enforceable equivalent contract here.
    if failures:
        print("APPROVED_HTML_IMPLEMENTATION_AUDIT_FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1

    print("APPROVED_HTML_IMPLEMENTATION_AUDIT_PASS")
    print("  django_admin_canvas: implemented")
    print("  fix_review_packet: implemented")
    print("  tenant_option_a: implemented")
    print("  claude_artifact: represented by local tenant Option A preview")
    return 0


if __name__ == "__main__":
    sys.exit(main())
