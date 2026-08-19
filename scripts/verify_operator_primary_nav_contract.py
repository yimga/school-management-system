"""Verify operator primary nav proximity-rail contract.

Locks:
  1. manager_operator_topbar includes control_plane_primary_nav with rail=True
  2. proximity reveal script gated on data-rmc-proximity-reveal
  3. unified header is a single quiet band (no second <xl nav row)

Retired 2026-08-18 (Platform Clean Header Approval v2, user-approved SOT batch
1791–1792): the former "More" overflow dropdown requirement AND the former
``control_plane_unified_header`` <xl fallback nav row. v2 collapses the operator
band to one row; the rail lives in the utility topbar. Remaining destinations
live in Utilities.

Retired 2026-08-18 (Platform Clean Header Approval v2, user-approved SOT batch
1791–1792): the former "More" overflow dropdown requirement. v2 caps the operator
band at two inline pills and routes every remaining destination through the
Utilities dropdown, so there is no primary-nav overflow to fold into a "More" menu.
The old requirement was also mutually exclusive with verify_header_utilities_contract,
which forbids the ``data-rmc-cp-nav-more`` substring on the same file.

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

    if "cp-header__row--inline-chrome" in header:
        findings.append(
            "control_plane_unified_header.html: forbidden second-row <xl nav "
            "(Clean Header v2 — rail lives in the utility topbar)"
        )

    for needle in (
        "data-rmc-proximity-reveal",
    ):
        if needle not in nav:
            findings.append(f"control_plane_primary_nav.html: missing '{needle}'")

    for needle in (
        "cp-primary-nav--rail",
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
