#!/usr/bin/env python3
"""Verify Threshold Era procurement trust nav wiring (batch 1702)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    errors: list[str] = []
    partial = ROOT / "templates/marketing/partials/mkt_procurement_trust_nav.html"
    home = ROOT / "templates/marketing/threshold_era_home.html"
    css = ROOT / "static/marketing/css/mkt-revolution-lab.css"

    if not partial.is_file():
        errors.append("missing mkt_procurement_trust_nav.html")
    else:
        text = partial.read_text(encoding="utf-8")
        for needle in (
            "mkt-rev-trust-nav",
            "marketing_public_href",
            "marketing_pricing",
            "marketing_platform_security",
            "public_status",
        ):
            if needle not in text:
                errors.append(f"partial missing {needle}")

    if not home.is_file():
        errors.append("missing threshold_era_home.html")
    elif "mkt_procurement_trust_nav.html" not in home.read_text(encoding="utf-8"):
        errors.append("threshold_era_home.html does not include procurement nav partial")

    if not css.is_file():
        errors.append("missing mkt-revolution-lab.css")
    elif ".mkt-rev-trust-nav" not in css.read_text(encoding="utf-8"):
        errors.append("mkt-revolution-lab.css missing .mkt-rev-trust-nav rules")

    if errors:
        for err in errors:
            print(f"MARKETING_PROCUREMENT_TRUST_NAV_FAIL: {err}")
        return 1

    print("MARKETING_PROCUREMENT_TRUST_NAV_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
