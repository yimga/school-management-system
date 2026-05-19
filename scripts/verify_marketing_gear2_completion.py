#!/usr/bin/env python3
"""Repo-contained gate: marketing gear-up items 1–7 (lanes, homepage motion, geo, conversion)."""
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "apps/schools/marketing_geo.py",
    "static/marketing/css/marketing-gear2-home.css",
    "static/marketing/css/marketing-gear2-lanes.css",
    "static/marketing/js/mkt-day-role-toggle.js",
    "static/marketing/js/mkt-globe-tooltips.js",
    "static/marketing/js/mkt-admissions-steps.js",
    "templates/marketing/components/_hero_geo_subline.html",
    "templates/marketing/components/_day_role_story.html",
    "templates/marketing/components/_globe_tooltips.html",
    "templates/marketing/components/_proof_quote.html",
    "templates/marketing/components/_lane_academics_matrix.html",
    "templates/marketing/components/_lane_admissions_steps.html",
    "templates/marketing/components/_lane_finance_ledger.html",
    "scripts/verify_marketing_production_smoke.py",
    "tests/e2e/marketing-pricing-i18n.spec.js",
)

LANDING_SNIPPETS = (
    "marketing-gear2-home.css",
    "_hero_geo_subline.html",
    "_day_role_story.html",
    "mkt-edt-globe__map--interactive",
    "_globe_tooltips.html",
    "_proof_quote.html",
    "marketing_carousel_items",
    "mkt-day-role-toggle.js",
    "mkt-globe-tooltips.js",
)

LANE_SNIPPETS = {
    "templates/marketing/pages/type_platform_student_information_system.html": (
        "marketing-gear2-lanes.css",
        "_lane_academics_matrix.html",
    ),
    "templates/marketing/pages/type_platform_admissions.html": (
        "marketing-gear2-lanes.css",
        "_lane_admissions_steps.html",
        "mkt-admissions-steps.js",
    ),
    "templates/marketing/pages/type_platform_fees_payments.html": (
        "marketing-gear2-lanes.css",
        "_lane_finance_ledger.html",
    ),
}

SCROLL_NARRATIVE_SNIPPETS = (
    "data-bell-auto-ms",
    "ArrowRight",
    "startAuto",
)


def main() -> int:
    missing: list[str] = []

    for rel in REQUIRED_FILES:
        if not (REPO / rel).is_file():
            missing.append(f"missing file: {rel}")

    landing = (REPO / "templates/schools/marketing_landing_v2.html").read_text(encoding="utf-8")
    for snippet in LANDING_SNIPPETS:
        if snippet not in landing:
            missing.append(f"landing missing: {snippet}")

    bell = (REPO / "templates/marketing/components/_bell_clock_sticky.html").read_text(
        encoding="utf-8"
    )
    if "data-bell-auto-ms" not in bell:
        missing.append("bell clock missing data-bell-auto-ms")

    scroll = (REPO / "static/marketing/js/scroll-narrative.js").read_text(encoding="utf-8")
    for snippet in SCROLL_NARRATIVE_SNIPPETS:
        if snippet not in scroll:
            missing.append(f"scroll-narrative missing: {snippet}")

    views = (REPO / "apps/schools/marketing_views.py").read_text(encoding="utf-8")
    if "marketing_geo_tagline" not in views or "marketing_geo import" not in views:
        missing.append("marketing_views missing geo wiring")

    manifest = (REPO / "scripts/marketing_css_bundle_manifest.json").read_text(encoding="utf-8")
    if "marketing-gear2-lanes.css" not in manifest:
        missing.append("bundle manifest missing marketing-gear2-lanes.css")

    for rel, snippets in LANE_SNIPPETS.items():
        text = (REPO / rel).read_text(encoding="utf-8")
        for snippet in snippets:
            if snippet not in text:
                missing.append(f"{rel} missing: {snippet}")

    if missing:
        for item in missing:
            print(f"FAIL: {item}", file=sys.stderr)
        return 1

    print("OK: verify_marketing_gear2_completion — gear-up 1–7 repo slice complete")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
