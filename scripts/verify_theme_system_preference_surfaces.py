#!/usr/bin/env python3
"""
System-preference theme contract (v3): System resolves to light OR dark effective surface.

Validates remediate engine per effective surface (not one hex on both — impossible for
harsh yellow/green). Matches docs/THEME_SYSTEM.md: data-theme is never raw "system".
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from apps.siteconfig.brand_guard_runtime import DARK_SURFACE, LIGHT_SURFACE
from apps.siteconfig.contrast_guard import remediate_brand_hex_on_background

HARSH_BRANDS = ("#ffff00", "#00ff00", "#ff00ff", "#4f46e5")
MIN_AAA = 7.0

EFFECTIVE_SURFACES = {
    "light": LIGHT_SURFACE,
    "dark": DARK_SURFACE,
    "system_resolves_light": LIGHT_SURFACE,
    "system_resolves_dark": DARK_SURFACE,
}


def main() -> int:
    failures: list[str] = []
    for theme_mode, surface in EFFECTIVE_SURFACES.items():
        for brand in HARSH_BRANDS:
            result = remediate_brand_hex_on_background(
                brand, surface, min_ratio=MIN_AAA
            )
            ratio = float(result.get("remediated_ratio") or 0)
            if not result.get("ok") or ratio < MIN_AAA:
                failures.append(
                    f"{theme_mode}/{brand} on {surface}: ratio={ratio}"
                )
    if failures:
        print("verify_theme_system_preference_surfaces: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1
    print(
        f"verify_theme_system_preference_surfaces: PASS "
        f"({len(HARSH_BRANDS)} brands x {len(EFFECTIVE_SURFACES)} effective surfaces)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
