#!/usr/bin/env python3
"""Verify manager /super/ v8 200x landing contract (v3.90.62).

Guards against regressions where:
  - a 200x cockpit section stops reaching the landing at all
  - 200x cockpit sections are wrapped in collapsible <details> (localStorage
    collapse -> empty ruled bands while cockpit health still says would_render)
  - rmc-data-viz.css clobbers lx-heatmap__grid display:flex over display:grid

Section presence is resolved through the TEMPLATE INCLUDE GRAPH rooted at
super_dashboard.html, not by grepping super_dashboard.html for a literal path.
That distinction is load-bearing: v4.05.62 (WOW v2 globe deck) moved
``partials/cockpit/_live_world_map.html`` one include deeper, behind
``partials/cockpit/_globe_deck_v2_shell.html``, and
``scripts/verify_globe_wow_v2_deck_parity.py`` now FORBIDS the direct include
that the old literal check here still demanded. Both gates cannot be satisfied
at once, so this one asserts reachability instead of spelling.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SUPER_DASH_REL = "schools/super_dashboard.html"
SUPER_DASH = ROOT / "templates" / SUPER_DASH_REL
DATA_VIZ = ROOT / "static" / "css" / "rmc-data-viz.css"
CP_200X = ROOT / "static" / "css" / "rmc-cp-200x.css"

# Markers that must appear in super_dashboard.html itself (landing chrome).
REQUIRED_LANDING_MARKERS = (
    'data-rmc-cp-200x-landing="1"',
    'class="lx-cols-2"',
)

# Sections that must remain REACHABLE from the landing, at any include depth.
REQUIRED_LANDING_PARTIALS = (
    "partials/cockpit/_live_world_map.html",
    "partials/cockpit/_slo_clocks.html",
    "partials/cockpit/_tenant_heatmap.html",
    "partials/cockpit/_revenue_waterfall.html",
    "partials/cockpit/_audit_feed.html",
)

COLLAPSABLE = "partials/cockpit/_collapsable_section.html"

FORBIDDEN_IN_LANDING = (
    "super__live_world_map",
    "super__slo_clocks",
    "super__tenant_heatmap",
    "super__revenue_waterfall",
    "super__audit_feed",
)

COMMENT_RE = re.compile(r"{%\s*comment\b.*?%}.*?{%\s*endcomment\s*%}", re.DOTALL)
INCLUDE_RE = re.compile(r'{%\s*include\s+"([^"]+)"')
INCLUDE_PARTIAL_RE = re.compile(r'include_partial="([^"]+)"')
COLLAPSABLE_TAG_RE = re.compile(
    r'{%\s*include\s+"' + re.escape(COLLAPSABLE) + r'"(.*?)%}', re.DOTALL
)
LANDING_BLOCK_RE = re.compile(
    r'class="rmc-cp-200x-landing"[^>]*>(.*?)</div>\s*\n'
    r"{% comment %} v3\.58\.x Wave 10 Agent S",
    re.DOTALL,
)


def _template_roots() -> list[Path]:
    roots = [ROOT / "templates"]
    apps_dir = ROOT / "apps"
    if apps_dir.is_dir():
        for app in sorted(apps_dir.iterdir()):
            candidate = app / "templates"
            if candidate.is_dir():
                roots.append(candidate)
    return roots


def _resolve(rel: str, roots: list[Path]) -> Path | None:
    for root in roots:
        candidate = root / rel
        if candidate.is_file():
            return candidate
    return None


def _strip_comments(text: str) -> str:
    return COMMENT_RE.sub("", text)


def _include_graph(start_rel: str) -> tuple[set[str], dict[str, str]]:
    """Return (reachable template names, name -> comment-stripped source)."""
    roots = _template_roots()
    reachable: set[str] = set()
    sources: dict[str, str] = {}
    stack = [start_rel]
    while stack:
        rel = stack.pop()
        if rel in reachable:
            continue
        reachable.add(rel)
        path = _resolve(rel, roots)
        if path is None:
            continue
        body = _strip_comments(path.read_text(encoding="utf-8", errors="replace"))
        sources[rel] = body
        for match in INCLUDE_RE.finditer(body):
            stack.append(match.group(1))
        for match in INCLUDE_PARTIAL_RE.finditer(body):
            stack.append(match.group(1))
    return reachable, sources


def main() -> int:
    errors: list[str] = []

    dash = SUPER_DASH.read_text(encoding="utf-8")
    for marker in REQUIRED_LANDING_MARKERS:
        if marker not in dash:
            errors.append(f"super_dashboard.html missing {marker!r}")

    reachable, sources = _include_graph(SUPER_DASH_REL)
    for partial in REQUIRED_LANDING_PARTIALS:
        if partial not in reachable:
            errors.append(
                f"super_dashboard.html include graph no longer reaches {partial!r}"
            )
        elif partial not in sources:
            errors.append(f"{partial!r} is included but the template file is missing")

    # A required section must not arrive wrapped in the collapsible <details>
    # helper, at ANY depth -- that is the localStorage-collapse regression this
    # gate exists for, and moving an include one level deeper used to hide it.
    for rel, body in sorted(sources.items()):
        for tag_args in COLLAPSABLE_TAG_RE.findall(body):
            for wrapped in INCLUDE_PARTIAL_RE.findall(tag_args):
                if wrapped in REQUIRED_LANDING_PARTIALS:
                    errors.append(
                        f"{rel}: 200x landing section {wrapped!r} is wrapped in "
                        f"{COLLAPSABLE}"
                    )

    landing_match = LANDING_BLOCK_RE.search(dash)
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
    if COLLAPSABLE in landing_block:
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
