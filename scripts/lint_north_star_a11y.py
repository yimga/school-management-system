#!/usr/bin/env python3
"""
North star N3/N4 — Accessibility and touch targets.

RUNMYCAMPUS North star: WCAG 2.1 AA hints (skip links, viewport, focus) and
touch targets ≥44px for interactive elements. This script runs static checks:
- Base shells include accessibility.css (phase_h_audit also checks responsive CSS).
- Optional: scan CSS for button/link min dimensions < 44px (touch target heuristic).

Use --strict to exit 1 when a required check fails. Run after phase_h_audit.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATIC_CSS = ROOT / "static" / "css"
TEMPLATES = ROOT / "templates"

# Touch target minimum (WCAG 2.5.5 Level AAA suggests 44x44 CSS pixels)
TOUCH_TARGET_MIN_PX = 44


def check_accessibility_css_in_bases(failures: list[str]) -> None:
    """Ensure base shells reference accessibility.css."""
    bases = [
        ("base.html", TEMPLATES / "base.html"),
        ("control_plane_skeleton.html", TEMPLATES / "control_plane_skeleton.html"),
        ("portal_base.html", TEMPLATES / "portal_base.html"),
        (
            "marketing/base_marketing.html",
            TEMPLATES / "marketing" / "base_marketing.html",
        ),
    ]
    for name, path in bases:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "accessibility.css" not in text and "accessibility" not in text:
            failures.append(f"{name}: missing accessibility.css (North star N3)")


def scan_touch_targets_css(css_dir: Path, min_px: int) -> list[tuple[Path, int, str]]:
    """Heuristic: find button/input/select/textarea rules with min-height or min-width < min_px."""
    hits: list[tuple[Path, int, str]] = []
    for path in sorted(css_dir.rglob("*.css")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Look for .btn, button, input, select, textarea with min-height or min-width in px
        for i, line in enumerate(text.splitlines(), 1):
            if "min-height" in line or "min-width" in line:
                for num in re.findall(
                    r"min-(?:height|width)\s*:\s*[^;]*?(\d+)\s*px", line, re.I
                ):
                    if int(num) > 0 and int(num) < min_px:
                        hits.append(
                            (
                                path,
                                i,
                                f"min dimension {num}px < {min_px}px touch target (N4)",
                            )
                        )
                        break
    return hits


def main() -> int:
    ap = argparse.ArgumentParser(description="North star N3/N4: a11y and touch targets")
    ap.add_argument("--strict", action="store_true", help="Exit 1 on any failure")
    ap.add_argument(
        "--touch", action="store_true", help="Scan CSS for touch target heuristics"
    )
    args = ap.parse_args()

    failures: list[str] = []
    check_accessibility_css_in_bases(failures)

    if failures:
        for f in failures:
            print(f"FAIL: {f}", file=sys.stderr)
        if args.strict:
            return 1

    if args.touch:
        hits = scan_touch_targets_css(STATIC_CSS, TOUCH_TARGET_MIN_PX)
        for path, line_no, msg in hits[:20]:  # cap output
            rel = path.relative_to(ROOT)
            print(f"{rel}:{line_no}: {msg}")
        if hits and args.strict:
            return 1

    if not failures and (not args.touch or not hits):
        print(
            "North star a11y lint: base shells include accessibility.css; touch scan optional."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
