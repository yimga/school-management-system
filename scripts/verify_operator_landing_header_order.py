#!/usr/bin/env python3
"""verify_operator_landing_header_order.py — operator workbench landings must show
their page header BEFORE optional cockpit chrome (pulse, globe, heatmap…).

Trigger: founder + customer-success dashboards stacked collapsable <details> rules
and a zero-operator presence capsule above the real page title — operators scrolled
past empty chrome to reach "Platform Command Center".

Zero-tolerance from introduction 2026-08-22. Stdlib only.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(_HERE)
MARKER = "landing-header-order-allow"

# Templates that carry optional cockpit stacks AND a primary page header.
LANDING_MARKERS = (
    "data-rmc-founder-dashboard",
    "data-rmc-operational-workbench",
)

HEADER_MARKERS = (
    "rmc-page-header-glow",
    'include "studio_os/components/page_header.html"',
    'include "components/world_class_page_hero.html"',
    "rmc_page_masthead.html",
)

CHROME_MARKERS = (
    "partials/cockpit/_collapsable_section.html",
    "partials/cockpit/_operator_presence.html",
    "partials/cockpit/_platform_pulse.html",
    "partials/cockpit/_live_world_map.html",
)


def _read(path: str) -> str:
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read()


def _first_index(src: str, needles: tuple[str, ...]) -> int | None:
    hits = [src.find(n) for n in needles if n in src]
    return min(hits) if hits else None


def _has_allow_marker(src: str) -> bool:
    return MARKER in src


def scan(root: str) -> list[dict]:
    findings: list[dict] = []
    templates_root = os.path.join(root, "templates")
    for dirpath, _, filenames in os.walk(templates_root):
        for fn in filenames:
            if not fn.endswith(".html"):
                continue
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace("\\", "/")
            src = _read(full)
            if not any(m in src for m in LANDING_MARKERS):
                continue
            if _has_allow_marker(src):
                continue
            header_idx = _first_index(src, HEADER_MARKERS)
            chrome_idx = _first_index(src, CHROME_MARKERS)
            if header_idx is None or chrome_idx is None:
                continue
            if chrome_idx < header_idx:
                findings.append(
                    {
                        "file": rel,
                        "reason": (
                            "cockpit chrome appears before the page header on an "
                            "operator workbench landing — move the header block first"
                        ),
                    }
                )
    return sorted(findings, key=lambda f: f["file"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=REPO_ROOT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--strict", action="store_true")
    args = ap.parse_args()

    findings = scan(args.root)
    if args.json:
        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
    else:
        for f in findings:
            print(f"{f['file']}: {f['reason']}")
        print(f"operator-landing-header-order: {len(findings)} finding(s)")
    if args.strict and findings:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
