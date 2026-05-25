#!/usr/bin/env python3
"""Verify platform dropdown toggles use viewport-safe Bootstrap attrs + global fix assets."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / "templates"

REQUIRED_ATTRS = (
    "data-bs-boundary",
    "data-bs-display",
)

DROPDOWN_TOGGLE = re.compile(r'data-bs-toggle=["\']dropdown["\']')


def main() -> int:
    failures: list[str] = []

    chrome = ROOT / "templates/partials/rmc_platform_chrome_styles.html"
    boot = ROOT / "templates/partials/rmc_dropdown_viewport_safe_boot.html"
    css = ROOT / "static/css/rmc-dropdown-viewport-safe.css"
    js = ROOT / "static/js/rmc-dropdown-viewport-safe.js"
    for p in (chrome, boot, css, js):
        if not p.is_file():
            failures.append(f"missing asset: {p.relative_to(ROOT)}")

    user_dd = TEMPLATES / "components/user_dropdown.html"
    if user_dd.is_file():
        ud = user_dd.read_text(encoding="utf-8")
        if "data-bs-boundary" not in ud or "data-rmc-shell-viewport-safe" not in ud:
            failures.append("components/user_dropdown.html: header profile dropdown not hardened")

    ws = TEMPLATES / "components/rmc_operator_workspace_dropdown.html"
    if ws.is_file():
        wst = ws.read_text(encoding="utf-8")
        if "data-bs-boundary" not in wst:
            failures.append("components/rmc_operator_workspace_dropdown.html: workspace dropdown not hardened")

    if failures:
        print("verify_header_dropdown_viewport: FAIL", file=sys.stderr)
        for f in failures[:40]:
            print(f"  - {f}", file=sys.stderr)
        if len(failures) > 40:
            print(f"  ... and {len(failures) - 40} more", file=sys.stderr)
        return 1

    print("verify_header_dropdown_viewport: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
