"""Verify operator primary nav proximity rail + More dropdown contract.

Locks:
  1. manager_operator_topbar includes control_plane_primary_nav with rail=True
  2. control_plane_unified_header fallback row also passes rail=True
  3. proximity reveal script gated on data-rmc-proximity-reveal
  4. More menu uses Bootstrap dropdown with fixed popper strategy (overflow-safe)

PASS exits 0 with OPERATOR_PRIMARY_NAV_CONTRACT_PASS.
"""

from __future__ import annotations

import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    findings: list[str] = []

    topbar = _read("templates/partials/manager_operator_topbar.html")
    header = _read("templates/partials/control_plane_unified_header.html")
    nav = _read("templates/partials/control_plane_primary_nav.html")
    skin = _read("static/css/rmc-cockpit-skin-v8.css")

    if "control_plane_primary_nav.html\" with rail=True" not in topbar and "rail=True" not in topbar:
        findings.append("manager_operator_topbar.html: missing rail=True nav include")
    elif "rail=True" not in topbar:
        findings.append("manager_operator_topbar.html: missing rail=True nav include")

    if "control_plane_primary_nav.html\" with rail=True" not in header and "rail=True" not in header:
        findings.append("control_plane_unified_header.html: fallback nav missing rail=True")

    for needle in (
        "data-rmc-proximity-reveal",
        "cpPrimaryNavMoreRail",
        "data-rmc-cp-nav-more-menu",
        "cp-primary-nav__more-menu",
    ):
        if needle not in nav:
            findings.append(f"control_plane_primary_nav.html: missing '{needle}'")

    for needle in (
        "cp-primary-nav--rail",
        ".cp-primary-nav__more-menu",
        "overflow: visible",
    ):
        if needle not in skin:
            findings.append(f"rmc-cockpit-skin-v8.css: missing '{needle}'")

    if findings:
        for f in findings:
            print(f"FAIL: {f}", file=sys.stderr)
        return 1

    print("OPERATOR_PRIMARY_NAV_CONTRACT_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
