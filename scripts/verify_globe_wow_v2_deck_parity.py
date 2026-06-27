#!/usr/bin/env python3
"""Verify WOW v2 globe deck ships with zero-gap parity vs preview HTML contract."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

DECK_PARTIALS = (
    "templates/partials/cockpit/_globe_deck_v2_shell.html",
    "templates/partials/cockpit/_globe_deck_crown.html",
    "templates/partials/cockpit/_globe_deck_lens_nav.html",
    "templates/partials/cockpit/_globe_deck_rail_left.html",
    "templates/partials/cockpit/_globe_deck_rail_right.html",
)

REQUIRED_MARKERS: tuple[tuple[str, str], ...] = (
    ("templates/schools/super_dashboard.html", "data-rmc-cp-globe-deck-v2"),
    ("templates/schools/super_dashboard.html", "_globe_deck_v2_shell.html"),
    ("templates/partials/cockpit/_globe_deck_v2_shell.html", "data-rmc-cp-globe-deck-v2"),
    ("templates/partials/cockpit/_globe_deck_crown.html", "data-rmc-cp-landing-tab"),
    ("templates/partials/cockpit/_globe_deck_lens_nav.html", "data-rmc-section-anchor"),
    ("templates/partials/cockpit/_globe_deck_rail_left.html", "rmc-globe-deck-v2__pulse-mosaic"),
    ("templates/partials/cockpit/_globe_deck_rail_left.html", "rmc-globe-deck-v2__slo-bars"),
    ("templates/partials/cockpit/_globe_deck_rail_right.html", "rmc-globe-deck-v2__schools-ring"),
    ("templates/partials/cockpit/_globe_deck_rail_right.html", "rmc-world-globe-ai-guide-ask"),
    ("templates/partials/cockpit/_live_world_map.html", "lx-world-lab--globe-deck-v2"),
    ("static/css/rmc-cp-globe-deck-v2.css", "rmc-globe-deck-v2__frame"),
    ("static/js/rmc-globe-deck-v2.js", "data-rmc-globe-deck-proxy"),
    ("apps/schools/super_views_dashboard_surfaces.py", "rmc_cp_globe_deck_v2"),
)

RETIRED_ABOVE_GLOBE = (
    ("templates/schools/super_dashboard.html", 'class="rmc-section-nav rmc-page-fold-nav mb-2"'),
    ("templates/schools/super_dashboard.html", "rmc-cp-landing-mode__tabs mb-3"),
)


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    failures: list[str] = []

    for rel in DECK_PARTIALS:
        if not (ROOT / rel).is_file():
            failures.append(f"missing partial: {rel}")

    for rel, needle in REQUIRED_MARKERS:
        try:
            text = _read(rel)
        except OSError:
            failures.append(f"missing file: {rel}")
            continue
        if needle not in text:
            failures.append(f"{rel}: missing marker {needle!r}")

    super_html = _read("templates/schools/super_dashboard.html")
    if super_html.count("_live_world_map.html") > 0:
        failures.append("super_dashboard still includes _live_world_map.html directly (use deck shell)")

    for rel, needle in RETIRED_ABOVE_GLOBE:
        if needle in _read(rel):
            failures.append(f"{rel}: retired above-globe chrome still present ({needle!r})")

    rail_right = _read("templates/partials/cockpit/_globe_deck_rail_right.html")
    if "default:row.title" in rail_right:
        failures.append(
            "templates/partials/cockpit/_globe_deck_rail_right.html: "
            "uses default:row.title (Django resolves fallback args eagerly; use firstof)"
        )

    if failures:
        print("FAIL: globe WOW v2 deck parity", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        return 1

    print("OK: globe WOW v2 deck parity — all contract markers present")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
