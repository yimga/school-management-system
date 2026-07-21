#!/usr/bin/env python3
"""MAX Wave 4: twin masthead + work-root contract for money/setup/mission twins.

Asserts canonical templates include ``rmc_page_masthead`` and ``data-rmc-work-root``,
interactive mission role tabs, chip sparklines, and ops-frame composition.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    (
        "templates/schools/billing_dashboard.html",
        ("rmc_page_masthead.html", 'data-page-archetype="money"', "data-rmc-work-root"),
    ),
    (
        "templates/finance/dashboard.html",
        ("rmc_page_masthead.html", 'data-page-archetype="money"', "data-rmc-work-root"),
    ),
    (
        "templates/platform_runtime/school_configuration_center.html",
        ("rmc_page_masthead.html", 'data-page-archetype="setup"', "data-rmc-work-root"),
    ),
    (
        "templates/accounts/backend_dashboard.html",
        (
            "rmc_page_masthead.html",
            'data-page-archetype="mission"',
            "data-rmc-work-root",
            "rmc_mission_role_tabs.html",
            "mission_season",
        ),
    ),
    (
        "templates/schools/super_dashboard.html",
        (
            "rmc_page_masthead.html",
            'data-page-archetype="mission"',
            "data-rmc-work-root",
            "rmc_mission_role_tabs.html",
            "mission_season",
        ),
    ),
    (
        "templates/components/rmc_mission_role_tabs.html",
        ("mission_role", "tab.href", "data-rmc-mission-role-tabs"),
    ),
    (
        "templates/components/rmc_operational_center_frame.html",
        ("rmc_operational_center_frame_inner.html",),
    ),
    (
        "templates/components/rmc_operational_center_frame_inner.html",
        ("rmc_page_masthead.html", "data-rmc-work-root"),
    ),
    (
        "templates/components/rmc_page_masthead.html",
        ("data-rmc-page-masthead", "masthead_chips", "sparkline_points", "rmc-page-masthead__spark"),
    ),
)


def main() -> int:
    failed = []
    for rel, needles in REQUIRED:
        path = ROOT / rel
        if not path.exists():
            failed.append(f"MISSING {rel}")
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for needle in needles:
            if needle not in text:
                failed.append(f"{rel} missing {needle!r}")
    if failed:
        print("FAIL twin masthead contract:", file=sys.stderr)
        for f in failed:
            print(f"  {f}", file=sys.stderr)
        return 1
    print("OK: twin masthead / work-root contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
