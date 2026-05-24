#!/usr/bin/env python3
"""Fail when operational workbench templates still ship world_class_page_hero."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

# Pages that intentionally keep the tall hero (command center landing).
ALLOW_HERO = {
    "templates/schools/super_dashboard.html",
}

WORKBENCH_MARKERS = (
    'data-rmc-operational-workbench="1"',
    "data-rmc-operational-workbench='1'",
    "data-page-archetype=\"operational-workbench\"",
    "data-page-archetype='operational-workbench'",
)

HERO_SNIPPET = "world_class_page_hero.html"
FRAME_SNIPPET = "rmc_operational_center_frame.html"


def _rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def scan() -> list[str]:
    findings: list[str] = []
    for path in sorted(TEMPLATES.rglob("*.html")):
        rel = _rel(path)
        if rel in ALLOW_HERO:
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if HERO_SNIPPET not in text:
            continue
        if not any(marker in text for marker in WORKBENCH_MARKERS):
            continue
        if FRAME_SNIPPET in text:
            findings.append(f"{rel}: workbench has both hero and operational frame")
        else:
            findings.append(f"{rel}: workbench still uses world_class_page_hero")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    findings = scan()
    if args.json:
        import json

        print(json.dumps({"finding_count": len(findings), "findings": findings}, indent=2))
    elif findings:
        print(f"operational-workbench-surface: {len(findings)} finding(s)")
        for row in findings:
            print(f"  - {row}")
    else:
        print("operational-workbench-surface: OK (0 findings)")
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
