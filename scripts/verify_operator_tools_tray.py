#!/usr/bin/env python3
"""Verify Operator Tools edge-tray wiring on control-plane shells."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.parse_args()
    failures: list[str] = []

    skeleton = _read("templates/control_plane_skeleton.html")
    admin_site = _read("templates/admin/base_site.html")
    portal = _read("templates/portal_base.html")
    scripts_partial = _read("templates/partials/rmc_operator_tools_scripts.html")
    styles_partial = _read("templates/partials/rmc_operator_tools_styles.html")

    for needle in (
        "rmc_operator_tools_styles.html",
        "rmc_operator_tools_scripts.html",
    ):
        if needle not in skeleton:
            failures.append(f"control_plane_skeleton.html missing {needle}")

    for needle in (
        "rmc_operator_tools_styles.html",
        "rmc_operator_tools_scripts.html",
    ):
        if needle not in admin_site:
            failures.append(f"admin/base_site.html missing {needle}")

    if "page-data-rmc-operator-tools" in portal:
        failures.append("portal_base.html must not ship operator tools page data")

    if "rmc-operator-tools-tray.js" in portal:
        failures.append("portal_base.html must not ship operator tools tray JS")

    if "request.public_host_kind == 'manager'" not in scripts_partial:
        failures.append("rmc_operator_tools_scripts.html missing manager host gate")

    if 'data-rmc-back-to-top-policy="always"' in skeleton:
        failures.append("control_plane_skeleton still uses always-on back-to-top policy")

    slots_py = _read("apps/assist_dock/operator_tools_slots.py")
    if "operator-notebook" not in slots_py:
        failures.append("operator_tools_slots.py missing operator-notebook registration")

    js = _read("static/js/rmc-operator-tools-tray.js")
    if "data-rmc-assist-layout" not in js or "edge-tray" not in js:
        failures.append("rmc-operator-tools-tray.js missing edge-tray transform")
    if "admin-manager-shell" not in js:
        failures.append("rmc-operator-tools-tray.js missing admin-manager-shell surface gate")
    if "isAuthLanding" not in js:
        failures.append("rmc-operator-tools-tray.js missing auth landing guard")

    css = _read("static/css/rmc-operator-tools-tray.css")
    if ".rmc-operator-tools__edge-tab" not in css:
        failures.append("rmc-operator-tools-tray.css missing edge tab styles")

    cockpit = _read("apps/siteconfig/cockpit_manager_200x.py")
    if "operator_tools" not in cockpit:
        failures.append("cockpit_manager_200x.py missing operator_tools defaults")

    smoke = _read("scripts/smoke_operator_tools_tray.py")
    if "OPERATOR_TOOLS_SMOKE_PASS" not in smoke:
        failures.append("smoke_operator_tools_tray.py missing OPERATOR_TOOLS_SMOKE_PASS marker")

    if failures:
        for item in failures:
            print(f"FAIL: {item}")
        return 1

    print("OK: operator tools edge-tray contract")
    return 0


if __name__ == "__main__":
    sys.exit(main())
