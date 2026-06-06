#!/usr/bin/env python3
"""Portal/control-plane shell load-performance invariants (blocking assets diet)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

CHECKS: tuple[tuple[str, str, str], ...] = (
    (
        "templates/portal_base.html",
        r"vendor/react/react\.production\.min\.js",
        "global React stack must not load on every portal page",
    ),
    (
        "templates/portal_base.html",
        r"fonts\.googleapis\.com",
        "blocking Google Fonts CDN in portal shell",
    ),
    (
        "templates/control_plane_skeleton.html",
        r"fonts\.googleapis\.com",
        "blocking Google Fonts CDN in control-plane shell",
    ),
    (
        "templates/portal_base.html",
        r'shell-data-dashboard-page\.js"[^>]*>\s*</script>',
        "shell-data-dashboard-page.js must use defer",
    ),
    (
        "templates/portal_base.html",
        r'kb-route-signature\.js"[^>]*>\s*</script>',
        "kb-route-signature.js must use defer",
    ),
    (
        "templates/portal_base.html",
        r'bootstrap\.bundle\.min\.js"[^>]*>\s*</script>',
        "bootstrap.bundle must use defer in portal shell",
    ),
    (
        "templates/partials/rmc_platform_chrome_scripts.html",
        r'rmc-cp-chrome-offset\.js"[^>]*>\s*</script>',
        "rmc-cp-chrome-offset.js must use defer",
    ),
)


def main() -> int:
    failures: list[str] = []
    for rel, pattern, message in CHECKS:
        path = REPO / rel
        text = path.read_text(encoding="utf-8")
        for match in re.finditer(pattern, text):
            if " defer" in match.group(0):
                continue
            failures.append(f"{rel}: {message}")
            break

    portal = (REPO / "templates/portal_base.html").read_text(encoding="utf-8")
    if "portal-shell-enhanced.min.css" not in portal:
        failures.append(
            "templates/portal_base.html: missing deferred portal-shell-enhanced.min.css bundle"
        )
    if portal.count("rmc-sidebar-luxury-10x.css") > 1:
        failures.append(
            "templates/portal_base.html: duplicate rmc-sidebar-luxury-10x.css load"
        )

    dual_plane_count = portal.count("rmc_theme_experience_dual_plane_styles.html")
    if dual_plane_count > 1:
        failures.append(
            f"templates/portal_base.html: dual-plane styles included {dual_plane_count}x "
            "(expected once at terminal cascade)"
        )

    if failures:
        print("verify_portal_shell_load_performance: FAIL", file=sys.stderr)
        for line in failures:
            print(f"  {line}", file=sys.stderr)
        return 1

    print("verify_portal_shell_load_performance: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
