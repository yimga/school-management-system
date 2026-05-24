#!/usr/bin/env python3

"""Tenant portal v3 100x parity gate (batch 1481 + 1484 role-home depth).



Checks portal_base tenant branch for preview header grammar, role-home hero

includes, legacy dashboard de-dupe gates, and v3 role-home shell contract.

"""



from __future__ import annotations



import sys

from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent



ROLE_HOME_CHECKS = (

    (

        "templates/parent/dashboard.html",

        "parent_show_legacy_dashboard",

        'class="parent-dashboard',

    ),

    (

        "templates/teacher/dashboard.html",

        "teacher_show_legacy_dashboard",

        'class="tdm-bg"',

    ),

    (

        "templates/accounts/backend_dashboard.html",

        "backend_show_legacy_dashboard",

        "backend-dashboard-content",

    ),

)





def _text(rel: str) -> str:

    path = ROOT / rel

    return path.read_text(encoding="utf-8", errors="replace") if path.is_file() else ""





def _check_legacy_gate(rel: str, gate_token: str, legacy_token: str) -> str | None:

    body = _text(rel)

    if not body:

        return f"missing {rel}"

    if "hero_greeting.html" not in body:

        return f"{rel}: missing hero_greeting.html include"

    if "tp-dashboard-cockpit" not in body:

        return None

    if legacy_token not in body:

        return None

    gate_idx = body.find(gate_token)

    legacy_idx = body.find(legacy_token)

    if gate_idx < 0 or legacy_idx < 0 or gate_idx > legacy_idx:

        return (

            f"{rel}: legacy block must be gated behind {gate_token} "

            f"(before {legacy_token})"

        )

    return None





def main() -> int:

    findings: list[str] = []



    portal = _text("templates/portal_base.html")

    if not portal:

        findings.append("missing templates/portal_base.html")

        return _fail(findings)



    if "tp-header__row" not in portal:

        findings.append("portal_base.html: missing tp-header__row (tenant v3 preview)")

    if "tenant_primary_nav" not in portal and "tp-primary-nav" not in portal:

        findings.append("portal_base.html: missing tp-primary-nav / tenant_primary_nav include")

    if "data-rmc-tp-v3-role-home" not in portal:

        findings.append("portal_base.html: missing data-rmc-tp-v3-role-home shell contract")

    if "rmc-tenant-v3-100x-role-home.css" not in portal:

        findings.append("portal_base.html: missing rmc-tenant-v3-100x-role-home.css wiring")

    if "tp_v3_role_home" not in portal:

        findings.append("portal_base.html: missing tp_v3_role_home dedupe gates")



    if 'class="navbar navbar-dark topbar' in portal or "navbar-dark topbar" in portal:

        findings.append(

            "portal_base.html: legacy navbar-dark topbar still present — remove for v3"

        )



    css_header = ROOT / "static/css/rmc-tenant-header-100x.css"

    if not css_header.is_file():

        findings.append("missing static/css/rmc-tenant-header-100x.css")



    role_home_css = ROOT / "static/css/rmc-tenant-v3-100x-role-home.css"

    if not role_home_css.is_file():

        findings.append("missing static/css/rmc-tenant-v3-100x-role-home.css")



    hero = ROOT / "templates/partials/tenant/hero_greeting.html"

    if not hero.is_file():

        findings.append("missing templates/partials/tenant/hero_greeting.html (tp-hero-row)")

    else:

        hero_text = hero.read_text(encoding="utf-8", errors="replace")

        if "tp_hero_ai_tier_line" not in hero_text:

            findings.append("hero_greeting.html: missing tp_hero_ai_tier_line (PII-safe tier)")

        if "tp_hero_contextual_line" not in hero_text:

            findings.append("hero_greeting.html: missing tp_hero_contextual_line")



    backend_tpl = _text("templates/accounts/backend_dashboard.html")

    if "backend_show_legacy_dashboard" in backend_tpl and "backend-dashboard-v2.css" in backend_tpl:

        if "{% if backend_show_legacy_dashboard %}" not in backend_tpl:

            findings.append(

                "backend_dashboard.html: backend-dashboard-v2.css must be gated behind legacy flag"

            )



    shell_js = _text("static/js/shell-data-dashboard-page.js")

    if "data-rmc-tp-v3-role-home" not in shell_js:

        findings.append("shell-data-dashboard-page.js: missing v3 role-home classifier guard")

    if "data-rmc-tp-v3-shell" not in shell_js:

        findings.append("shell-data-dashboard-page.js: missing v3 tenant-shell classifier guard")



    proc = _text("apps/portal/context_processors.py")

    if "def tp_v3_role_home" not in proc:

        findings.append("context_processors.py: missing tp_v3_role_home processor")



    helper = _text("apps/portal/tenant_role_home.py")

    if "is_tp_v3_role_home_request" not in helper:

        findings.append("tenant_role_home.py: missing is_tp_v3_role_home_request")

    if "is_tp_v3_tenant_shell_request" not in helper:

        findings.append("tenant_role_home.py: missing is_tp_v3_tenant_shell_request")

    if "tp_v3_tenant_shell" not in portal:

        findings.append("portal_base.html: missing tp_v3_tenant_shell shell contract")

    if "data-rmc-tp-v3-shell" not in portal:

        findings.append("portal_base.html: missing data-rmc-tp-v3-shell attribute")

    if not (ROOT / "apps/portal/tenant_cockpit_enrichment.py").is_file():

        findings.append("missing apps/portal/tenant_cockpit_enrichment.py")

    if "tp-community-band" not in _text("templates/partials/cockpit/_community_band.html"):

        findings.append("_community_band.html: missing tp-community-band preview class")

    if "tp_brand_surface_pill" not in helper:

        findings.append("tenant_role_home.py: missing tp_brand_surface_pill helper")

    if not (ROOT / "templates/partials/tenant/tp_header_brand.html").is_file():

        findings.append("missing templates/partials/tenant/tp_header_brand.html")

    if not (ROOT / "templates/partials/tenant/tp_breadcrumb.html").is_file():

        findings.append("missing templates/partials/tenant/tp_breadcrumb.html")

    if "tp_header_brand.html" not in portal:

        findings.append("portal_base.html: missing tp_header_brand include on v3 tenant shell")

    if "tp_breadcrumb.html" not in portal:

        findings.append("portal_base.html: missing tp_breadcrumb include on v3 role home")

    if "tp-canvas-body" not in portal:

        findings.append("portal_base.html: missing tp-canvas-body canvas wrapper")

    def _gated_on_v3_shell(needle: str) -> bool:
        idx = portal.find(needle)
        if idx < 0:
            return True
        window = portal[max(0, idx - 320) : idx + 120]
        return "not tp_v3_tenant_shell" in window

    for needle, label in (
        ("portal-chathead", "floating chathead"),
        ("components/ai_copilot.html", "floating AI copilot"),
        ("lifecycle_concierge_enabled", "lifecycle concierge"),
        ("proactive_help_nudge", "proactive help nudge"),
        ("dashboard_stats_cards", "dashboard stats cards"),
    ):
        if not _gated_on_v3_shell(needle):
            findings.append(
                f"portal_base.html: {label} must gate on tp_v3_tenant_shell"
            )

    if "rmc-tp-pulse-sheet.js" not in portal:

        findings.append("portal_base.html: missing rmc-tp-pulse-sheet.js on v3 tenant shell")

    if not (ROOT / "apps/portal/tenant_cockpit_realdata.py").is_file():

        findings.append("missing apps/portal/tenant_cockpit_realdata.py")

    role_home_css_text = _text("static/css/rmc-tenant-v3-100x-role-home.css")

    if "body.tp-v3-inner .studio-os-topbar" not in role_home_css_text:

        findings.append(

            "rmc-tenant-v3-100x-role-home.css: missing inner-page studio-os-topbar dedupe"

        )

    if "prefers-reduced-motion" not in role_home_css_text:

        findings.append(

            "rmc-tenant-v3-100x-role-home.css: missing prefers-reduced-motion quick-tile rules"

        )

    for rel, gate, legacy in ROLE_HOME_CHECKS:

        err = _check_legacy_gate(rel, gate, legacy)

        if err:

            findings.append(err)



    if findings:

        return _fail(findings)



    print("verify_preview_shell_100x_tenant_parity: PREVIEW_SHELL_TENANT_V3_PARITY_PASS")

    return 0





def _fail(findings: list[str]) -> int:

    print("verify_preview_shell_100x_tenant_parity: FAIL", file=sys.stderr)

    for item in findings:

        print(f"  - {item}", file=sys.stderr)

    return 1





if __name__ == "__main__":

    raise SystemExit(main())

