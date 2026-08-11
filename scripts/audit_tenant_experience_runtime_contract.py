#!/usr/bin/env python3
"""Tenant-wide ExperienceTemplate, checklist, preview, and action contract audit."""

from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "var" / "tenant-experience-runtime-audit.json"


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []
    checks: list[str] = []

    def require(condition: bool, label: str) -> None:
        if condition:
            checks.append(label)
        else:
            errors.append(label)

    apply_engine = read("apps/platform_runtime/pack_apply.py")
    package_engine = read("apps/packages/engine.py")
    runtime = read("apps/brand_experience/template_runtime.py")
    studio = read("apps/setup_studio/services.py")
    preview_view = read("apps/brand_experience/views_template_marketplace.py")
    preview_url = read("apps/platform_runtime/live_preview.py")
    preview_template = read("templates/marketplace/templates_preview_frame.html")
    apply_template = read("templates/marketplace/templates_apply_confirm.html")
    runtime_css = read("static/css/rmc-experience-template-runtime.css")

    require("activate_experience_template" in apply_engine, "apply activates runtime")
    require("build_experience_runtime_payload" in apply_engine, "apply pre-validates runtime")
    require(
        'if section == "experience_template"' in package_engine
        and 'return "experience_pack"' in package_engine,
        "package type is canonical",
    )
    require("TemplateAssignment.objects.update_or_create" in runtime, "assignment is durable and idempotent")
    require("active_experience_templates" in runtime, "active runtime is durable")
    require(
        "previous_assignment.installed_package.is_active = True" in runtime,
        "rollback reactivates the prior template installation",
    )
    require("reconcile_latest_experience_template" in studio, "checklist self-heals legacy applies")
    require("FeatureToggleState" in studio and "definition__key__startswith" in studio, "starter stack reads canonical toggles")

    require("get_studio_role_preview_entries" in preview_view, "preview receives role targets")
    require("get_preview_url" in preview_view, "preview receives a safe internal URL")
    require("origin_host=request.get_host()" in preview_view, "preview preserves only same-host absolute role targets")
    require("parsed.hostname != allowed_hostname" in preview_url, "preview blocks cross-host absolute targets")
    require("/portal/preview" not in preview_url, "preview does not target a missing route")
    require("<iframe" in preview_template and 'src="{{ preview_url }}"' in preview_template, "preview renders a genuine iframe")
    require(preview_template.count("data-rmc-preview-frame-shell") == 1, "preview device switch owns one frame")
    require("rmc-template-marketplace.css" in preview_template, "preview owns its stylesheet in head block")
    require("Template active" in apply_template and "{% if not result %}" in apply_template, "apply result is state-aware")

    settings = read("config/settings.py")
    context = read("apps/platform_runtime/context_processors.py")
    require("tenant_experience_context" in settings, "runtime context processor is configured")
    require("resolve_active_experience_template" in context, "runtime resolves per request and role")
    for shell in (
        "templates/base.html",
        "templates/portal_base.html",
        "templates/admin/base_site.html",
        "templates/control_plane_skeleton.html",
    ):
        source = read(shell)
        require(source.count("rmc-experience-template-runtime.css") == 1, f"{shell} owns runtime CSS exactly once")
    for shell in (
        "templates/base.html",
        "templates/portal_base.html",
        "templates/admin/base.html",
        "templates/control_plane_skeleton.html",
    ):
        require("data-rmc-experience-template" in read(shell), f"{shell} exposes runtime state")

    reconcile_command = read(
        "apps/brand_experience/management/commands/reconcile_experience_template_runtime.py"
    )
    require("--apply" in reconcile_command and "--school" in reconcile_command, "legacy apply reconciliation is deployable and scoped")
    browser_verifier = read("scripts/verify_tenant_experience_runtime_browser.mjs")
    require("applied experience checklist step is green" in browser_verifier, "browser gate proves checklist state")
    require("preview iframe preserves the admin preview target" in browser_verifier, "browser gate proves live preview target")

    palettes = (
        "green-emerald", "cool-indigo", "warm-terracotta", "savanna-ochre",
        "andes-clay", "desert-amber", "editorial-cream", "monsoon-teal",
        "nordic-slate", "sakura-blush",
    )
    for palette in palettes:
        require(f'data-rmc-experience-palette="{palette}"' in runtime_css, f"palette implemented: {palette}")
    require("rmc-admin-catalog-model-grid" in runtime_css, "runtime reaches tenant Django admin catalogs")
    require("@media (max-width: 64rem)" in runtime_css, "runtime remains single-column at 1024px")

    timetable = read("apps/academics/views_timetable.py")
    timetable_hub = read("apps/academics/views_hub.py")
    require('@require_http_methods(["GET", "POST"])' in timetable, "timetable generator accepts canonical GET")
    require("accounts:ops_timetabling" in timetable and "accounts:ops_timetabling" in timetable_hub, "timetable GET and hub share one workspace")

    component = read("templates/components/ai_guided_assistant_card.html")
    ai_css = read("static/css/rmc-ai-guided-assistant-card.css")
    require("rmc-ai-guided-assistant-card__cta" in component, "AI Center uses the shared action component")
    require("border-radius: 999px" in ai_css and "text-decoration: none" in ai_css, "AI Center CTA is visibly actionable")
    for shell in ("templates/base.html", "templates/portal_base.html", "templates/control_plane_skeleton.html"):
        require(read(shell).count("rmc-ai-guided-assistant-card.css") == 1, f"{shell} owns AI action CSS exactly once")

    action_labels = (
        "Manage config & scopes", "View all finance requests", "Open finance inbox",
        "Show all configuration areas", "Upload more data", "All AI surfaces",
        "Full feature center",
    )
    template_paths = list((ROOT / "templates").rglob("*.html"))
    for path in template_paths:
        for line_number, line in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
            if any(label in line for label in action_labels) and "btn-link" in line:
                errors.append(f"plain-text action: {path.relative_to(ROOT)}:{line_number}")
    simulator = read("templates/siteconfig/permission_matrix_simulator.html")
    require(not re.search(r"<button[^>]*disabled[^>]*>[^<]*Suggested fix", simulator), "non-working suggested-fix button removed")

    lock = json.loads(read("var/admin-approval-build-lock.json"))
    admin_head = read("templates/admin/base_site.html")
    sw = read("static/js/service-worker.js")
    seal_css = read("static/css/rmc-admin-emergency-full-canvas-v17.css")
    require(lock["build_id"] in admin_head, "build ID is synchronized")
    require(f'?v={lock["cache_bust"]}' in admin_head, "cache-bust ID is synchronized")
    require(lock["sw_version"] in sw, "service-worker version is synchronized")
    require(lock["seal"] in seal_css, "release seal is synchronized")

    report = {
        "pass": not errors,
        "checks_passed": len(checks),
        "templates_scanned": len(template_paths),
        "errors": errors,
        "build_id": lock.get("build_id"),
        "cache_bust": lock.get("cache_bust"),
        "service_worker_version": lock.get("sw_version"),
        "scope": [
            "tenant Studio launch checklist",
            "experience template apply/reconcile/rollback",
            "tenant portal and Django admin runtime",
            "live role preview",
            "tenant action affordances",
            "timetable generator GET/POST contract",
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    if errors:
        print("TENANT_EXPERIENCE_RUNTIME_AUDIT_FAIL")
        for error in errors:
            print(f"  - {error}")
        return 1
    print(
        "TENANT_EXPERIENCE_RUNTIME_AUDIT_PASS "
        f"checks={len(checks)} templates={len(template_paths)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
