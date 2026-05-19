#!/usr/bin/env python3
"""
Theme calibration gate: Light/Dark surface matrix + WCAG 2.2 AAA (7:1) remediate engine.

Exercises remediate_brand_hex_on_background across representative brand/surface pairs
for both light and dark canvas backgrounds (System preference resolves to one of these
per docs/THEME_SYSTEM.md v3 effective-theme contract).
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.siteconfig.contrast_guard import (
    remediate_brand_hex_on_background,
    text_color_for_background,
)

# Representative school brand picks (intentionally harsh).
BRAND_SAMPLES = (
    "#ffff00",
    "#00ff00",
    "#ff00ff",
    "#4f46e5",
    "#10b981",
    "#f97316",
)

# Light + dark effective surfaces (not raw preference=system).
SURFACES = {
    "light": "#ffffff",
    "dark": "#0f172a",
}

MIN_AAA = 7.0


def main() -> int:
    failures: list[str] = []
    for theme_mode, surface in SURFACES.items():
        for brand in BRAND_SAMPLES:
            result = remediate_brand_hex_on_background(
                brand, surface, min_ratio=MIN_AAA
            )
            fg = text_color_for_background(surface, min_ratio=MIN_AAA)
            ratio = float(result.get("remediated_ratio") or 0)
            if not result.get("ok") or ratio < MIN_AAA:
                failures.append(
                    f"{theme_mode}/{brand} on {surface}: "
                    f"ratio={ratio} remediated={result.get('remediated_hex')}"
                )
            if not fg:
                failures.append(f"{theme_mode}/{surface}: no readable foreground")

    if failures:
        print("verify_theme_aaa_brand_cycle: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1

    print(
        f"verify_theme_aaa_brand_cycle: PASS "
        f"({len(BRAND_SAMPLES)} brands x {len(SURFACES)} surfaces @ {MIN_AAA}:1)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
