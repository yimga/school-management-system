#!/usr/bin/env python3
"""Gate: five marketing personality viewport pages + registry + routes."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

PERSONALITY_TEMPLATES = (
    "templates/marketing/homepage.html",
    "templates/marketing/academics.html",
    "templates/marketing/edge_mesh.html",
    "templates/marketing/compliance.html",
    "templates/marketing/pricing.html",
)

REQUIRED_SLUGS = ("academics", "edge-mesh", "compliance", "pricing")


def main() -> int:
    findings: list[str] = []

    for rel in PERSONALITY_TEMPLATES:
        path = REPO / rel
        if not path.is_file():
            findings.append(f"missing {rel}")
            continue
        text = path.read_text(encoding="utf-8")
        if "marketing-visual-engine.css" not in text and rel.endswith("homepage.html"):
            pass
        if rel != "templates/marketing/homepage.html":
            if "data-mkt-personality-page=" not in text:
                findings.append(f"{rel}: missing data-mkt-personality-page")
            if 'data-rmc-scroll-policy="viewport-lock"' not in text:
                findings.append(f"{rel}: missing viewport-lock scroll policy")
        if "marketing_copy" not in text and "marketing_media" not in text:
            if rel != "templates/marketing/homepage.html":
                findings.append(f"{rel}: missing marketing_copy / marketing_media load")

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

    css = REPO / "static/marketing/css/marketing-personality-pages.css"
    if not css.is_file():
        findings.append("missing marketing-personality-pages.css")
    manifest = REPO / "scripts/marketing_css_bundle_manifest.json"
    if manifest.is_file() and "marketing-personality-pages.css" not in manifest.read_text(
        encoding="utf-8"
    ):
        findings.append("marketing_css_bundle_manifest.json missing personality CSS")

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

    matrix = (REPO / "apps/schools/marketing_media_matrix.py").read_text(encoding="utf-8")
    for token in (
        "txt_academics_headline",
        "txt_edge_headline",
        "txt_compliance_headline",
        "txt_pricing_headline",
    ):
        if token not in matrix:
            findings.append(f"MARKETING_COPY_REGISTRY missing {token}")

    if findings:
        print("verify_marketing_personality_pages: FAIL", file=sys.stderr)
        for item in findings:
            print(f"  - {item}", file=sys.stderr)
        return 1

    print("verify_marketing_personality_pages: MARKETING_PERSONALITY_PAGES_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
