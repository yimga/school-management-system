#!/usr/bin/env python3
"""Gate: marketing personality viewport pages + acquisition engine slices."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PERSONALITY_TEMPLATES = (
    "templates/marketing/homepage.html",
    "templates/marketing/zero_ui_lab.html",
    "templates/marketing/enterprise_ledger.html",
    "templates/marketing/academics.html",
    "templates/marketing/edge_mesh.html",
    "templates/marketing/compliance.html",
    "templates/marketing/pricing.html",
)

REQUIRED_SLUGS = (
    "zero-ui",
    "enterprise-ledger",
    "academics",
    "edge-mesh",
    "compliance",
    "pricing",
)

ACQUISITION_PARTIALS = (
    "templates/marketing/partials/sections/_hero_speed_duel.html",
    "templates/marketing/partials/sections/_hero_edge_map.html",
    "templates/marketing/partials/sections/_zero_ui_lab.html",
    "templates/marketing/partials/sections/_viewport_trinity.html",
    "templates/marketing/partials/sections/_enterprise_constellation.html",
)

ACQUISITION_JS = (
    "static/marketing/js/mkt-speed-duel.js",
    "static/marketing/js/mkt-edge-map.js",
    "static/marketing/js/mkt-zero-ui-playground.js",
    "static/marketing/js/mkt-viewport-trinity.js",
    "static/marketing/js/mkt-enterprise-constellation.js",
)


def main() -> int:
    findings: list[str] = []

    for rel in PERSONALITY_TEMPLATES:
        path = REPO / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if rel != "templates/marketing/homepage.html":
            if "data-mkt-personality-page=" not in text:
                findings.append(f"{rel}: missing data-mkt-personality-page")
            if 'data-rmc-scroll-policy="viewport-lock"' not in text:
                findings.append(f"{rel}: missing viewport-lock scroll policy")
        if "marketing_copy" not in text and "marketing_media" not in text:
            if rel != "templates/marketing/homepage.html":
                findings.append(f"{rel}: missing marketing_copy / marketing_media load")

    for rel in ACQUISITION_PARTIALS:
        if not (REPO / rel).is_file():
            findings.append(f"missing acquisition partial {rel}")

    homepage = REPO / "templates/marketing/homepage.html"
    if homepage.is_file():
        hp = homepage.read_text(encoding="utf-8")
        if "_hero_speed_duel.html" not in hp:
            findings.append("homepage.html missing _hero_speed_duel.html")
        if "marketing-acquisition-engine.css" not in hp:
            findings.append("homepage.html missing acquisition CSS")
        if "mkt-speed-duel.js" not in hp:
            findings.append("homepage.html missing mkt-speed-duel.js")
        if "mkt-edge-map.js" not in hp:
            findings.append("homepage.html missing mkt-edge-map.js")

    edge = REPO / "templates/marketing/edge_mesh.html"
    if edge.is_file() and "_viewport_trinity.html" not in edge.read_text(encoding="utf-8"):
        findings.append("edge_mesh.html missing _viewport_trinity.html")

    for rel in ACQUISITION_JS:
        if not (REPO / rel).is_file():
            findings.append(f"missing {rel}")

    css = REPO / "static/marketing/css/marketing-acquisition-engine.css"
    if not css.is_file():
        findings.append("missing marketing-acquisition-engine.css")

    registry = REPO / "apps/schools/marketing_personality_registry.py"
    if not registry.is_file():
        findings.append("missing marketing_personality_registry.py")
    else:
        reg_text = registry.read_text(encoding="utf-8")
        for slug in REQUIRED_SLUGS:
            if f'"{slug}"' not in reg_text:
                findings.append(f"registry missing slug {slug}")

    urls = (REPO / "config/public_urls.py").read_text(encoding="utf-8")
    if "marketing_personality_page" not in urls:
        findings.append("public_urls.py missing marketing_personality_page route")
    if "experience/<slug:personality_slug>/" not in urls:
        findings.append("public_urls.py missing experience/ personality path")

    personality_css = REPO / "static/marketing/css/marketing-personality-pages.css"
    if not personality_css.is_file():
        findings.append("missing marketing-personality-pages.css")
    manifest = REPO / "scripts/marketing_css_bundle_manifest.json"
    manifest_text = manifest.read_text(encoding="utf-8") if manifest.is_file() else ""
    if manifest.is_file() and "marketing-personality-pages.css" not in manifest_text:
        findings.append("marketing_css_bundle_manifest.json missing personality CSS")
    acquisition_css = REPO / "static/marketing/css/marketing-acquisition-engine.css"
    if not acquisition_css.is_file():
        findings.append("missing marketing-acquisition-engine.css (page-level load)")

    fluid = REPO / "templates/marketing/partials/sections/_fluid_classroom.html"
    if fluid.is_file():
        ft = fluid.read_text(encoding="utf-8")
        if "mkt-ve-section--viewport-lock" not in ft:
            findings.append("_fluid_classroom.html: missing viewport-lock")
        if 'marketing_copy "txt_academics_headline"' not in ft:
            findings.append("_fluid_classroom.html: missing academics copy token")

    for partial in ("_governance_auditor_gateway.html", "_entitlement_calculator.html"):
        p = REPO / "templates/marketing/partials/sections" / partial
        if not p.is_file():
            findings.append(f"missing sections/{partial}")

    views = (REPO / "apps/schools/marketing_views.py").read_text(encoding="utf-8")
    if "def marketing_personality_page" not in views:
        findings.append("marketing_views.py missing marketing_personality_page")
    if "marketing_intent_homepage" not in views:
        findings.append("marketing_views.py missing marketing_intent_homepage nav wiring")

    verb_nav = (REPO / "apps/schools/marketing_v3_surfaces.py").read_text(encoding="utf-8")
    if "marketing_intent_homepage" not in verb_nav:
        findings.append("marketing_v3_surfaces.py missing storefront nav link")

    inventory = REPO / "apps/schools/marketing_url_inventory.py"
    if inventory.is_file():
        inv_text = inventory.read_text(encoding="utf-8")
        if "iter_marketing_acquisition_smoke_targets" not in inv_text:
            findings.append("marketing_url_inventory missing acquisition smoke iterator")
        for slug in ("zero-ui", "enterprise-ledger"):
            if slug not in inv_text:
                findings.append(f"marketing_url_inventory missing slug {slug}")

    matrix = (REPO / "apps/schools/marketing_media_matrix.py").read_text(encoding="utf-8")
    for token in (
        "txt_academics_headline",
        "txt_edge_headline",
        "txt_compliance_headline",
        "txt_pricing_headline",
        "txt_speed_duel_headline",
        "txt_zero_ui_headline",
        "txt_trinity_headline",
        "txt_enterprise_headline",
    ):
        if token not in matrix:
            findings.append(f"MARKETING_COPY_REGISTRY missing {token}")

    viz = (REPO / "apps/schools/templatetags/marketing_media.py").read_text(encoding="utf-8")
    if "enterprise_constellation_viz" not in viz:
        findings.append("marketing_media.py missing enterprise_constellation_viz")

    if findings:
        print("verify_marketing_personality_pages: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_marketing_personality_pages: MARKETING_PERSONALITY_PAGES_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
