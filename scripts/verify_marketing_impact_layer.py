#!/usr/bin/env python3
"""Gate for v3.37.1 marketing impact layer (bell/persona/globe/hero/lanes)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

REQUIRED_FILES = (
    "static/marketing/css/marketing-impact.css",
    "static/marketing/css/marketing-media-viz.css",
    "static/marketing/js/mkt-live-campus-pulse.js",
    "static/marketing/js/mkt-video-portal.js",
    "static/marketing/js/mkt-walkthrough-play.js",
    "static/marketing/js/mkt-lane-chrome.js",
    "static/marketing/js/mkt-page-personality.js",
    "static/marketing/css/marketing-page-personality.css",
    "templates/marketing/components/_hero_live_campus_pulse.html",
    "templates/marketing/components/_hero_media_showcase.html",
    "templates/marketing/components/_video_portal.html",
)

REQUIRED_SNIPPETS: tuple[tuple[str, str, str], ...] = (
    ("templates/schools/marketing_landing_v2.html", "_hero_media_showcase.html", "hero media showcase on homepage"),
    ("templates/schools/marketing_landing_v2.html", "marketing-impact.css", "impact CSS on homepage"),
    ("templates/schools/marketing_landing_v2.html", "marketing-media-viz.css", "media/viz CSS on homepage"),
    ("templates/schools/marketing_landing_v2.html", "mkt-walkthrough-play.js", "walkthrough play script on homepage"),
    ("templates/partials/rmc_analytics_viz_mount.html", "data-use-seeder", "analytics seeder attribute on mount"),
    ("apps/schools/marketing_views.py", "ANALYTICS_VIZ_USE_SEEDER", "marketing context enables analytics seeder"),
    ("templates/marketing/components/_video_portal.html", "data-mkt-video-overlay", "video play overlay on portal"),
    ("templates/schools/marketing_landing_v2.html", "_day_role_story.html", "day|role story toggle on homepage"),
    ("templates/schools/marketing_landing_v2.html", "_hero_geo_subline.html", "geo hero subline on homepage"),
    ("templates/schools/marketing_landing_v2.html", "mkt-edt-globe__map--interactive", "interactive globe map"),
    ("templates/marketing/components/_bell_clock_sticky.html", "data-bell-auto-ms", "bell auto-advance interval"),
    ("templates/marketing/components/_bell_clock_sticky.html", 'data-mkt-bell-clock-mode="single"', "single-panel bell clock"),
    ("templates/marketing/components/_bell_clock_sticky.html", "mkt-v3-dashboard-frame--impact", "constrained dashboard frames"),
    ("templates/marketing/components/_persona_tabs.html", "mkt-v3-persona-tabs--impact", "impact persona layout"),
    ("templates/marketing/base_marketing.html", "mkt-lane-chrome.js", "lane chrome script in shell"),
    ("templates/marketing/base_marketing.html", "mkt-page-personality.js", "page personality script in shell"),
    ("templates/marketing/base_marketing.html", "data-mkt-personality", "personality attribute on html"),
    ("templates/marketing/base_marketing.html", "marketing-page-personality.css", "personality CSS in shell"),
    ("static/marketing/js/scroll-narrative.js", "singleMode", "scroll narrative single-panel mode"),
    ("static/marketing/css/tokens-marketing.css", "--accent-principal-emerald", "academics lane token"),
    ("static/marketing/css/tokens-marketing.css", "--accent-finance-gold", "finance lane token"),
    ("static/marketing/css/tokens-marketing.css", "--accent-admissions-indigo", "admissions lane token"),
    ("scripts/marketing_css_bundle_manifest.json", "marketing-impact.css", "impact CSS in bundle manifest"),
    ("config/public_urls.py", "marketing_academics_short", "/academics/ short route"),
    ("config/public_urls.py", "marketing_admissions_short", "/admissions/ short route"),
    ("config/public_urls.py", "marketing_finance_short", "/finance/ short route"),
)

FORBIDDEN_PATTERNS: tuple[tuple[str, str, str], ...] = (
    ("templates/schools/_v2/_decoration_world_map.svg.html", r'fill="#1F2937"', "dark labels on cinematic map"),
    ("templates/marketing", r"</?motion\b", "invalid motion element"),
)


def _read(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    errors: list[str] = []

    for rel in REQUIRED_FILES:
        if not (REPO / rel).is_file():
            errors.append(f"missing file: {rel}")

    for rel, needle, label in REQUIRED_SNIPPETS:
        path = REPO / rel
        if not path.is_file():
            errors.append(f"missing snippet file for {label}: {rel}")
            continue
        if needle not in _read(rel):
            errors.append(f"{label}: expected `{needle}` in {rel}")

    map_path = REPO / "templates/schools/_v2/_decoration_world_map.svg.html"
    if map_path.is_file():
        map_text = map_path.read_text(encoding="utf-8")
        if "mkt-world-map" not in map_text:
            errors.append("world map SVG missing mkt-world-map class")
        if "currentColor" not in map_text:
            errors.append("world map SVG labels must use currentColor for theme contrast")

    for root_rel, pattern, label in FORBIDDEN_PATTERNS:
        root = REPO / root_rel
        if root.is_file():
            if re.search(pattern, root.read_text(encoding="utf-8", errors="replace")):
                errors.append(f"forbidden pattern ({label}) in {root_rel}")
        elif root.is_dir():
            for path in root.rglob("*.html"):
                if re.search(pattern, path.read_text(encoding="utf-8", errors="replace")):
                    errors.append(f"forbidden pattern ({label}) in {path.relative_to(REPO)}")

    if errors:
        print("verify_marketing_impact_layer: FAIL", file=sys.stderr)
        for err in errors:
            print(f"  - {err}", file=sys.stderr)
        return 1

    print("verify_marketing_impact_layer: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
