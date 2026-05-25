#!/usr/bin/env python3
"""Verify manager /super/ v8 200x landing contract (v3.90.62).

Guards against regressions where:
  - 200x cockpit sections are wrapped in collapsible <details> (localStorage
    collapse → empty ruled bands while cockpit health still says would_render)
  - rmc-data-viz.css clobbers lx-heatmap__grid display:flex over display:grid
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPER_DASH = ROOT / "templates" / "schools" / "super_dashboard.html"
DATA_VIZ = ROOT / "static" / "css" / "rmc-data-viz.css"
CP_200X = ROOT / "static" / "css" / "rmc-cp-200x.css"

REQUIRED_LANDING_MARKERS = (
    'data-rmc-cp-200x-landing="1"',
    'partials/cockpit/_live_world_map.html',
    'partials/cockpit/_slo_clocks.html',
    'partials/cockpit/_tenant_heatmap.html',
    'partials/cockpit/_revenue_waterfall.html',
    'partials/cockpit/_audit_feed.html',
    'class="lx-cols-2"',
)

FORBIDDEN_IN_LANDING = (
    'super__live_world_map',
    'super__slo_clocks',
    'super__tenant_heatmap',
    'super__revenue_waterfall',
    'super__audit_feed',
)


def main() -> int:
    errors: list[str] = []

    dash = SUPER_DASH.read_text(encoding="utf-8")
    for marker in REQUIRED_LANDING_MARKERS:
        if marker not in dash:
            errors.append(f"super_dashboard.html missing {marker!r}")

    landing_match = re.search(
        r'class="rmc-cp-200x-landing"[^>]*>(.*?)</div>\s*\n{% comment %} v3\.58\.x Wave 10 Agent S',
        dash,
        re.DOTALL,
    )
    if not landing_match:
        # fallback: slice between landing opener and trust_pillars comment
        start = dash.find('class="rmc-cp-200x-landing"')
        end = dash.find("{% comment %} v3.58.x Wave 10 Agent S")
        landing_block = dash[start:end] if start != -1 and end != -1 else ""
    else:
        landing_block = landing_match.group(1)

    for forbidden in FORBIDDEN_IN_LANDING:
        if forbidden in landing_block:
            errors.append(
                f"200x landing still uses collapsible localStorage key {forbidden!r}"
            )
    if "_collapsable_section.html" in landing_block:
        errors.append("200x landing must not include _collapsable_section.html wrappers")

    css = DATA_VIZ.read_text(encoding="utf-8")
    if ".lx-heatmap__grid.rmc-heatmap" not in css or "display: grid" not in css:
        errors.append("rmc-data-viz.css missing lx-heatmap grid guard")

    cp_css = CP_200X.read_text(encoding="utf-8")
    if ".rmc-cp-200x-landing" not in cp_css:
        errors.append("rmc-cp-200x.css missing .rmc-cp-200x-landing stack rules")

    if errors:
        print("CP_200X_LANDING_CONTRACT_FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1

    print("CP_200X_LANDING_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
