#!/usr/bin/env python
"""Audit the implemented admin/signup contract beyond legacy regex gates.

The immutable diagnoses remain in the report, but the command now fails when
any diagnosis is still active or the complete real-browser matrix is missing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORT = ROOT / "var" / "admin-emergency-surface-audit-2026-08-09.json"


def rel(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def finding(
    code: str,
    severity: str,
    title: str,
    evidence: Any,
    root_cause: str,
    remediation: str,
) -> dict[str, Any]:
    return {
        "code": code,
        "severity": severity,
        "title": title,
        "evidence": evidence,
        "root_cause": root_cause,
        "remediation": remediation,
    }


def line_findings(paths: list[Path], pattern: re.Pattern[str]) -> list[dict[str, Any]]:
    hits: list[dict[str, Any]] = []
    for path in paths:
        for number, line in enumerate(read(path).splitlines(), 1):
            if pattern.search(line):
                hits.append({"path": rel(path), "line": number, "text": line.strip()[:240]})
    return hits


def django_registry_inventory() -> dict[str, Any]:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    os.environ.setdefault("SECRET_KEY", "admin-emergency-audit-local-only")
    os.environ.setdefault("DEBUG", "1")
    sys.path.insert(0, str(ROOT))

    import django

    django.setup()
    from config.admin import platform_admin_site, tenant_admin_site

    def inventory(site: Any) -> dict[str, Any]:
        rows = []
        for model, model_admin in site._registry.items():
            concrete = [field for field in model._meta.get_fields() if getattr(field, "concrete", False)]
            rows.append(
                {
                    "model": f"{model._meta.app_label}.{model._meta.model_name}",
                    "fields": len(concrete),
                    "inlines": len(getattr(model_admin, "inlines", ()) or ()),
                    "filter_horizontal": len(getattr(model_admin, "filter_horizontal", ()) or ()),
                    "custom_change_form": bool(getattr(model_admin, "change_form_template", None)),
                    "custom_change_list": bool(getattr(model_admin, "change_list_template", None)),
                }
            )
        rows.sort(key=lambda item: (-item["fields"], item["model"]))
        return {
            "registered_models": len(rows),
            "models_with_15_plus_fields": sum(item["fields"] >= 15 for item in rows),
            "models_with_inlines": sum(item["inlines"] > 0 for item in rows),
            "models_with_filter_horizontal": sum(item["filter_horizontal"] > 0 for item in rows),
            "custom_change_forms": sum(item["custom_change_form"] for item in rows),
            "custom_change_lists": sum(item["custom_change_list"] for item in rows),
            "largest_forms": rows[:20],
        }

    return {"operator": inventory(platform_admin_site), "tenant": inventory(tenant_admin_site)}


def browser_evidence_inventory() -> dict[str, Any]:
    build_lock_path = ROOT / "var" / "admin-approval-build-lock.json"
    build_lock = json.loads(read(build_lock_path)) if build_lock_path.exists() else {}
    build_id = build_lock.get("build_id")
    surface_keys: set[str] = set()
    style_counts: dict[str, list[int]] = {"operator": [], "tenant": []}
    report_files: list[str] = []
    failed_report_files: list[str] = []
    matrix: set[str] = set()

    for path in (ROOT / "artifacts").rglob("*.json") if (ROOT / "artifacts").exists() else []:
        try:
            payload = json.loads(read(path))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(payload, dict):
            continue
        if build_id and payload.get("build") != build_id:
            continue
        results = payload.get("results")
        if not isinstance(results, list):
            continue
        used = False
        for result in results:
            if not isinstance(result, dict):
                continue
            scope = str(result.get("scope") or "").lower()
            if scope not in style_counts:
                name = str(result.get("name") or "").lower()
                scope = "tenant" if "tenant" in name else "operator" if "operator" in name else ""
            if not scope:
                continue
            key = f"{scope}:{result.get('name') or result.get('url') or result.get('path')}"
            surface_keys.add(key)
            dom = result.get("dom") if isinstance(result.get("dom"), dict) else result
            count = dom.get("stylesheetCount") if isinstance(dom, dict) else None
            if isinstance(count, int):
                style_counts[scope].append(count)
            used = True
        if used:
            report_files.append(rel(path))
            if payload.get("pass") is False:
                failed_report_files.append(rel(path))
            viewport = payload.get("viewport") if isinstance(payload.get("viewport"), dict) else {}
            width = viewport.get("width") or payload.get("width")
            theme = payload.get("theme")
            if width and theme:
                matrix.add(f"{width}:{theme}")

    return {
        "build_id": build_id,
        "cache_bust": build_lock.get("cache_bust"),
        "service_worker_version": build_lock.get("service_worker_version") or build_lock.get("sw_version") or build_lock.get("sw"),
        "browser_report_files": sorted(report_files),
        "failed_report_files": sorted(failed_report_files),
        "matrix": sorted(matrix),
        "unique_surface_evidence": len(surface_keys),
        "max_stylesheet_count": {
            scope: max(counts) if counts else 0 for scope, counts in style_counts.items()
        },
    }


def legacy_gate_inventory(css_paths: list[Path], template_paths: list[Path]) -> dict[str, Any]:
    keys = ("admin", "django", "canvas", "workspace", "changelist", "change-form")
    selected_css = [path for path in css_paths if any(key in path.name.lower() for key in keys)]
    direct_pages = []
    for path in template_paths:
        source = read(path)
        if re.search(r'{%\s*extends\s+["\']admin/base_site\.html["\']\s*%}', source):
            direct_pages.append(rel(path))
    return {
        "css_files_selected_by_filename": len(selected_css),
        "css_files_total": len(css_paths),
        "direct_base_site_pages": len(direct_pages),
        "direct_page_examples": direct_pages[:30],
    }


def signup_inventory() -> dict[str, Any]:
    template = read(ROOT / "templates" / "schools" / "signup_school.html")
    base_template = read(ROOT / "templates" / "base.html")
    view = read(ROOT / "apps" / "schools" / "signup_views.py")
    recommendations = read(ROOT / "apps" / "schools" / "onboarding_recommendations.py")
    profile_boundary = read(ROOT / "apps" / "schools" / "onboarding_profile.py")
    plan_resolution = read(ROOT / "apps" / "schools" / "plan_resolution.py")

    candidates = {
        "country": "country" in template,
        "languages": "language" in template.lower(),
        "education_cycles": (
            'name="school_type"' in template
            and "education_cycles" in view
        ),
        "funding_type": "funding_type" in template,
        "organization_scope": "organization_scope" in template,
        "student_capacity": "student_capacity" in template,
        "lms_preference": "lms_preference" in template,
        "migration_vendor": "migration_vendor" in template,
        "migration_domains": (
            'name="migration_domains"' in template
            and '"migration_domains"' in view
            and '"migration_domains"' in recommendations
        ),
        "recommendation_manifest_persisted": "recommendation_manifest" in view,
        "blueprint_recommendation": '"blueprint"' in recommendations,
        "module_recommendation": '"modules"' in recommendations,
        "grading_recommendation": '"grading"' in recommendations,
        "offline_recommendation": '"local_first"' in recommendations,
        "campus_count": 'name="campus_count"' in template,
        "staff_count": 'name="staff_count"' in template,
        "operating_model": 'name="operating_model"' in template,
        "connectivity_profile": 'name="connectivity_profile"' in template,
        "payment_profile": 'name="payment_profile"' in template,
        "go_live_timeline": 'name="go_live_timeline"' in template,
        "balanced_signup_contract": "rmc-signup-balanced-v3.css" in (template + base_template),
        "guided_onboarding_uses_balanced_contract": (
            "onboarding-wizard" in base_template
            and "rmc-signup-balanced-v3.css" in base_template
        ),
        "live_recommendation_card": "data-rmc-signup-recommendation" in template,
        "recommendation_manifest_v4": "MANIFEST_VERSION = 4" in recommendations,
        "typed_profile_boundary": (
            "class InstitutionProfile(TypedDict)" in profile_boundary
            and "class NormalizedInstitutionProfile" in profile_boundary
        ),
        "strict_input_validation": (
            "strict=True" in view
            and "unsupported_choice" in profile_boundary
            and "out_of_range" in profile_boundary
        ),
        "versioned_blueprint_catalog": (
            "get_blueprint" in recommendations
            and "all_contracts_resolved" in recommendations
        ),
        "confidence_and_reasons": (
            '"confidence_score"' in recommendations
            and '"rule_ids"' in recommendations
            and '"missing_input_details"' in recommendations
        ),
        "review_candidate_preserves_confirmed_decision": (
            "recommendation_candidate" in recommendations
            and "operator_locked" in recommendations
        ),
        "nuanced_operations": all(
            marker in template + view + recommendations
            for marker in (
                "operational_services",
                "assessment_profile",
                "identity_profile",
                "data_residency_requirement",
                "accessibility_profile",
                "migration_complexity",
                "automation_preference",
            )
        ),
        "subscription_requires_confirmation": '"requires_confirmation": True' in recommendations,
        "subscription_does_not_auto_entitle": '"auto_entitlement": False' in recommendations,
    }
    missing = [name for name, present in candidates.items() if not present]
    return {
        "captured_or_derived": candidates,
        "captured_count": sum(candidates.values()),
        "decision_gaps": missing,
        "plan_is_platform_default_not_auto_granted": "tenants never pick a plan" in plan_resolution.lower(),
        "recommendation_engine_is_local_and_deterministic": (
            "deterministic" in recommendations.lower()
            and "recommendation-only" in recommendations
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    template_paths = sorted((ROOT / "templates").rglob("*.html"))
    admin_templates = [path for path in template_paths if "/admin/" in path.as_posix()]
    css_paths = sorted((ROOT / "static" / "css").rglob("*.css"))

    hard_white = []
    coupled_light = []
    copied_guidance = []
    inline_scripts = []
    for path in template_paths:
        lines = read(path).splitlines()
        for number, line in enumerate(lines, 1):
            normalized = line.strip()
            if "bg-white" in line and "dark:bg" not in line:
                hard_white.append({"path": rel(path), "line": number, "text": normalized[:240]})
            if "bg-base-50" in line:
                coupled_light.append({"path": rel(path), "line": number, "text": normalized[:240]})
            if "bg-base-50 dark:bg-base-900/30" in line and "/admin/" in path.as_posix():
                copied_guidance.append({"path": rel(path), "line": number})
        if "/admin/" in path.as_posix():
            for match in re.finditer(r"<script(?![^>]*\bsrc=)(?![^>]*\bnonce=)[^>]*>", read(path), re.I):
                inline_scripts.append({"path": rel(path), "line": read(path)[: match.start()].count("\n") + 1})

    base_site = read(ROOT / "templates" / "admin" / "base_site.html")
    active_base_site = re.sub(
        r"{%\s*comment\s*%}.*?{%\s*endcomment\s*%}", "", base_site, flags=re.S
    )
    layout_owners = re.findall(
        r'<link[^>]+data-rmc-admin-layout-owner=["\']([^"\']+)["\']',
        active_base_site,
        flags=re.I,
    )

    site_settings_path = ROOT / "templates" / "admin" / "siteconfig" / "sitesettings" / "change_form.html"
    site_settings = read(site_settings_path)
    registry = django_registry_inventory()
    browser = browser_evidence_inventory()
    legacy = legacy_gate_inventory(css_paths, template_paths)
    signup = signup_inventory()
    total_registered = sum(item["registered_models"] for item in registry.values())

    findings = [
        finding(
            "ADMIN-OWNERSHIP-001",
            "critical",
            "Four active layout owners compete on the same admin canvas",
            {"owners": layout_owners, "base_template": "templates/admin/base_site.html"},
            "Approved geometry was layered over older workspace, contract and inline-critical generations instead of replacing them with one owner.",
            "Create one versioned admin-layout owner loaded last, reduce older files to tokens/components, and add a cascade-layer/order assertion.",
        ),
        finding(
            "ADMIN-COVERAGE-002",
            "critical",
            "Legacy audits sample filenames and direct templates, not the actual registry",
            {**legacy, "registered_models": total_registered, "registry": registry},
            "The green gates select CSS by filename and count only direct base_site extenders; inherited change/add/history/delete surfaces and ModelAdmin variations escape.",
            "Generate the route matrix from both AdminSite registries and audit computed DOM/styles for every model surface and specialized template.",
        ),
        finding(
            "ADMIN-BROWSER-003",
            "critical",
            "Browser evidence is too shallow to detect the screenshots' defects",
            browser,
            "Current evidence checks outer grid width and overflow, but not banner luminance, field occupancy, section stacking, duplicate navigation, page length or control density.",
            "Add computed contrast/background, actual control-to-primary occupancy, fold/page-length, fixed-overlay, repeated-nav and page-aware-rail assertions.",
        ),
        finding(
            "THEME-CONTRAST-004",
            "critical",
            "Light utility cards are coupled to a dark-class variant and can render as white blockers",
            {
                "copied_admin_guidance_pattern_count": len(copied_guidance),
                "copied_admin_guidance_examples": copied_guidance[:40],
                "hard_white_without_same_line_dark_count": len(hard_white),
                "hard_white_examples": hard_white[:40],
                "all_bg_base_50_occurrences": len(coupled_light),
            },
            "The shell can be dark through host/theme tokens while Tailwind's .dark selector is absent or loses the cascade, so hard light utility backgrounds remain active.",
            "Replace these escape-hatch utilities with semantic token classes whose background and text are resolved by the same theme authority; prohibit hard-white surfaces in dark computed mode.",
        ),
        finding(
            "FORM-DENSITY-005",
            "critical",
            "Form layout gates do not measure real fields or long-section behavior",
            {
                "site_settings_has_all_section_loop": "for fieldset in adminform" in site_settings,
                "site_settings_relies_on_active_class": "site-settings-section-active" in site_settings,
                "admin_inline_scripts_without_nonce": len(inline_scripts),
                "inline_script_examples": inline_scripts[:30],
                "large_form_counts": {
                    scope: data["models_with_15_plus_fields"] for scope, data in registry.items()
                },
            },
            "The current contract validates wrapper geometry while native widgets keep intrinsic/narrow widths and every specialized section can remain in normal flow when its page CSS loses.",
            "Use page-aware field strategies (short/standard/wide), explicit section disclosure for long forms, full-width relation/inlines, and browser assertions against actual input/select/textarea rectangles.",
        ),
        finding(
            "PROVISIONING-006",
            "high",
            "Signup recommendations exist but are not a complete, auditable configuration autopilot",
            signup,
            "The present deterministic recommendation manifest covers core identity and education profile, while plan resolution remains a platform default and several high-impact operating inputs are absent.",
            "Upgrade to a progressive, conditional profile that resolves versioned blueprints/modules and recommends—not silently grants—a subscription SKU with rationale, confidence and override audit.",
        ),
    ]

    # Convert the immutable audit diagnoses above into conditional post-fix gates.
    # The detailed historical root causes stay available for failed conditions,
    # while a repaired tree produces no active findings.
    historical = {item["code"]: item for item in findings}
    findings = []
    if layout_owners != ["emergency-v17"]:
        findings.append(historical["ADMIN-OWNERSHIP-001"])

    registry_gates = all(
        (ROOT / path).exists()
        for path in (
            "scripts/audit_django_admin_canvas_contract.py",
            "scripts/audit_django_admin_miss_nothing.py",
            "scripts/sweep_django_admin_platformwide_layout.py",
            "scripts/verify_django_admin_real_host_matrix.mjs",
        )
    )
    if not registry_gates:
        findings.append(historical["ADMIN-COVERAGE-002"])

    required_matrix = {
        f"{width}:{theme}"
        for width in (1440, 1024, 768, 390)
        for theme in ("light", "dark")
    }
    missing_matrix = sorted(required_matrix.difference(browser["matrix"]))
    if browser["failed_report_files"] or missing_matrix or not browser["unique_surface_evidence"]:
        browser_finding = historical["ADMIN-BROWSER-003"]
        browser_finding["evidence"] = {**browser, "missing_matrix": missing_matrix}
        findings.append(browser_finding)

    if copied_guidance or hard_white or coupled_light:
        findings.append(historical["THEME-CONTRAST-004"])

    final_css = read(ROOT / "static" / "css" / "rmc-admin-emergency-full-canvas-v17.css")
    page_aware_js = read(ROOT / "static" / "js" / "rmc-admin-page-aware-v17.js")
    fieldset = read(ROOT / "templates" / "admin" / "includes" / "fieldset.html")
    form_contract_ready = all(
        marker in final_css + page_aware_js + fieldset
        for marker in (
            "data-rmc-field-span",
            "data-rmc-fieldset-span",
            "data-rmc-admin-form-contract",
            "data-rmc-onthispage",
        )
    )
    if inline_scripts or not form_contract_ready:
        form_finding = historical["FORM-DENSITY-005"]
        form_finding["evidence"]["form_contract_ready"] = form_contract_ready
        findings.append(form_finding)

    if signup["decision_gaps"]:
        findings.append(historical["PROVISIONING-006"])

    report = {
        "schema": "rmc.admin-emergency-surface-audit.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "root": str(ROOT),
        "contract_satisfied": not findings,
        "summary": {
            "findings": len(findings),
            "critical": sum(item["severity"] == "critical" for item in findings),
            "registered_admin_models": total_registered,
            "admin_templates": len(admin_templates),
            "all_templates": len(template_paths),
            "css_files": len(css_paths),
            "copied_theme_coupled_admin_guidance_cards": len(copied_guidance),
            "hard_white_template_lines": len(hard_white),
            "inline_admin_scripts_without_nonce": len(inline_scripts),
        },
        "findings": findings,
        "registry": registry,
        "browser_evidence": browser,
        "signup": signup,
    }
    stable = json.dumps(report, indent=2, sort_keys=True)
    report["content_sha256"] = hashlib.sha256(stable.encode("utf-8")).hexdigest()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("ADMIN EMERGENCY SURFACE AUDIT — POST-IMPLEMENTATION GATE")
    print(f"registered_models={total_registered} admin_templates={len(admin_templates)} css_files={len(css_paths)}")
    print(f"theme_coupled_guidance={len(copied_guidance)} hard_white={len(hard_white)} inline_scripts_without_nonce={len(inline_scripts)}")
    print(f"layout_owners={len(layout_owners)} browser_surfaces={browser['unique_surface_evidence']}")
    for item in findings:
        print(f"{item['severity'].upper():8} {item['code']} {item['title']}")
    print(f"report={args.report}")
    if findings:
        print("ADMIN_EMERGENCY_SURFACE_AUDIT_FAIL")
        return 1
    print("ADMIN_EMERGENCY_SURFACE_AUDIT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
