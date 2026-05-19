#!/usr/bin/env python3
"""Verify advisory-board view-layer pages: definitions, URLs, templates, viz wiring."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from apps.schools.marketing_page_definitions import MARKETING_PAGE_DEFINITIONS  # noqa: E402
from apps.schools.marketing_view_layer_pages import (  # noqa: E402
    VIEW_LAYER_MARKETING_PAGE_SLUGS,
)

URLS_PY = REPO / "config" / "urls.py"

# slug -> url name (must exist in config/urls.py)
VIEW_LAYER_URL_NAMES: dict[str, str] = {
    "careers": "marketing_careers",
    "brand-assets": "marketing_brand_assets",
    "hardware-store": "marketing_hardware_store",
    "training-academies": "marketing_training_academies",
    "teacher-communities": "marketing_teacher_communities",
    "lesson-planning": "marketing_lesson_planning",
    "infrastructure-map": "marketing_infrastructure_map",
    "security-matrix": "marketing_security_matrix",
    "solutions-higher-ed": "marketing_solutions_higher_ed",
    "solutions-k12-districts": "marketing_solutions_k12_districts",
    "legal-ferpa": "marketing_legal_ferpa",
    "legal-coppa": "marketing_legal_coppa",
    "legal-gdpr": "marketing_legal_gdpr",
    "legal-wcag": "marketing_legal_wcag",
    "legal-terms": "marketing_legal_terms",
    "legal-cookie": "marketing_legal_cookie",
}


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []
    urls_text = URLS_PY.read_text(encoding="utf-8")

    if not (REPO / "templates/marketing/pages/type_view_layer.html").is_file():
        errors.append("missing type_view_layer.html")

    type_tpl = _read("templates/marketing/pages/type_view_layer.html")
    if "_personality_viz_panel.html" not in type_tpl:
        errors.append("type_view_layer missing viz panel")

    inner_head = _read("templates/marketing/partials/marketing_inner_head.html")
    if "marketing_personality" not in inner_head or "_personality_viz_panel.html" not in inner_head:
        errors.append("marketing_inner_head missing personality viz fallback")

    for slug in VIEW_LAYER_MARKETING_PAGE_SLUGS:
        if slug not in MARKETING_PAGE_DEFINITIONS:
            errors.append(f"MARKETING_PAGE_DEFINITIONS missing: {slug}")
        url_name = VIEW_LAYER_URL_NAMES.get(slug)
        if not url_name:
            errors.append(f"no URL name mapped for slug: {slug}")
            continue
        if f'name="{url_name}"' not in urls_text:
            errors.append(f"urls.py missing name={url_name} for {slug}")

    redirect_names = (
        "marketing_procurement_docs",
        "marketing_implementation_timelines",
        "marketing_portal_login",
        "marketing_find_campus_portal",
    )
    for name in redirect_names:
        if f'name="{name}"' not in urls_text:
            errors.append(f"urls.py missing redirect route: {name}")

    views = _read("apps/schools/marketing_views.py")
    if "VIEW_LAYER_MARKETING_PAGE_SLUGS" not in views or "type_view_layer.html" not in views:
        errors.append("marketing_views missing view-layer template routing")

    if errors:
        print("verify_marketing_view_layer_complete: FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1

    print(
        f"verify_marketing_view_layer_complete: OK ({len(VIEW_LAYER_MARKETING_PAGE_SLUGS)} pages, "
        f"{len(redirect_names)} aliases)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
