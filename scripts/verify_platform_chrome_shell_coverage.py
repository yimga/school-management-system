#!/usr/bin/env python3
"""Every canonical platform shell must wire shared chrome styles + scripts partials."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CANONICAL_SHELLS = (
    "templates/control_plane_skeleton.html",
    "templates/portal_base.html",
    "templates/admin/base_site.html",
    "templates/marketing/base_marketing.html",
    "templates/base.html",
)

STYLE_PARTIAL = "rmc_platform_chrome_styles.html"
SCRIPT_PARTIAL = "rmc_platform_chrome_scripts.html"


def main() -> int:
    errors: list[str] = []

    partial_styles = ROOT / "templates/partials/rmc_platform_chrome_styles.html"
    partial_scripts = ROOT / "templates/partials/rmc_platform_chrome_scripts.html"
    if not partial_styles.is_file():
        errors.append("missing templates/partials/rmc_platform_chrome_styles.html")
    else:
        body = partial_styles.read_text(encoding="utf-8")
        for asset in (
            "dashboard-topology-shell.css",
            "rmc-platform-chrome-layout.css",
            "rmc-platform-chrome-premium.css",
            "rmc-page-fold-standards.css",
        ):
            if asset not in body:
                errors.append(f"styles partial missing {asset}")
    if not partial_scripts.is_file():
        errors.append("missing templates/partials/rmc_platform_chrome_scripts.html")

    for rel in CANONICAL_SHELLS:
        text = (ROOT / rel).read_text(encoding="utf-8")
        if STYLE_PARTIAL not in text:
            errors.append(f"{rel}: missing styles partial include")
        if SCRIPT_PARTIAL not in text:
            errors.append(f"{rel}: missing scripts partial include")

    if errors:
        print("verify_platform_chrome_shell_coverage: FAIL")
        for err in errors:
            print(f"  - {err}")
        return 1
    print(
        f"verify_platform_chrome_shell_coverage: OK ({len(CANONICAL_SHELLS)} shells + partials)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
