#!/usr/bin/env python3
"""Audit dashboard date/time/weather placement — balanced layout contract."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CSS_FILE = ROOT / "static" / "css" / "rmc-calendar-weather-dashboard.css"
CAL_PARTIAL = ROOT / "templates" / "partials" / "cockpit" / "_calendar_weather.html"
HEADER_PARTIAL = ROOT / "templates" / "components" / "header_weather_widget.html"
MANAGER_TOPBAR = ROOT / "templates" / "partials" / "manager_operator_topbar.html"
PORTAL_BASE = ROOT / "templates" / "portal_base.html"
CP_BASE = ROOT / "templates" / "control_plane_base.html"

ROLE_HOME_DASHBOARDS = [
    ROOT / "templates" / "accounts" / "backend_dashboard.html",
    ROOT / "templates" / "teacher" / "dashboard.html",
    ROOT / "templates" / "parent" / "dashboard.html",
    ROOT / "templates" / "student" / "learning_home.html",
    ROOT / "templates" / "schools" / "super_dashboard.html",
]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    css = _read(CSS_FILE) if CSS_FILE.is_file() else ""
    if not CSS_FILE.is_file():
        failures.append("missing static/css/rmc-calendar-weather-dashboard.css")
    else:
        for needle in (
            ".tp-cal-weather__strip",
            "grid-template-columns: repeat(7",
            ".rmc-collapsable__body > .tp-cal-weather",
            ".rmc-platform-header__context",
        ):
            if needle not in css:
                failures.append(f"calendar weather CSS missing: {needle}")

    portal = _read(PORTAL_BASE)
    cp = _read(CP_BASE)
    if "rmc-calendar-weather-dashboard.css" not in portal:
        failures.append("portal_base.html must load rmc-calendar-weather-dashboard.css")
    if "rmc-calendar-weather-dashboard.css" not in cp:
        failures.append("control_plane_base.html must load rmc-calendar-weather-dashboard.css")

    cal = _read(CAL_PARTIAL)
    for needle in (
        "data-local-timezone",
        "data-rmc-cal-weather-now",
        "tp-cal-weather__strip",
        "rmc-calendar-weather-clock.js",
    ):
        if needle not in cal:
            failures.append(f"_calendar_weather.html missing: {needle}")
    if re.search(r'<section[^>]*style\s*=', cal):
        failures.append("_calendar_weather.html must not use inline style=")

    header = _read(HEADER_PARTIAL)
    if "data-local-timezone" not in header:
        failures.append("header_weather_widget.html missing data-local-timezone")
    if "data-header-datetime-global" not in header:
        failures.append("header_weather_widget.html missing global time node")

    topbar = _read(MANAGER_TOPBAR)
    if "rmc-platform-header__context" not in topbar:
        failures.append("manager topbar missing rmc-platform-header__context slot")
    if 'data-rmc-header-context-compact="1"' not in topbar:
        failures.append("manager topbar missing compact header context marker")
    if topbar.find('rmc-platform-header__actions') < topbar.find(
        "rmc-platform-header__context"
    ):
        failures.append(
            "manager context strip must appear before actions (search → datetime → actions)"
        )
    if 'SHOW_HEADER_CONTEXT_QUOTE=False' not in topbar:
        failures.append("manager topbar should disable quote in header context")

    for dash in ROLE_HOME_DASHBOARDS:
        if not dash.is_file():
            failures.append(f"missing dashboard template: {dash.relative_to(ROOT)}")
            continue
        text = _read(dash)
        if "_calendar_weather.html" not in text:
            failures.append(
                f"{dash.relative_to(ROOT)}: missing calendar weather partial include"
            )
        if dash.name == "super_dashboard.html":
            if 'data-rmc-dashboard-cal-weather="1"' not in text:
                failures.append("super_dashboard missing cal-weather slot wrapper")
            if "_collapsable_section.html" not in text or "super__calendar_weather" not in text:
                failures.append(
                    "super_dashboard must wrap calendar in collapsable section like tenant dashboards"
                )
        elif "_collapsable_section.html" not in text or "calendar_weather" not in text:
            failures.append(
                f"{dash.relative_to(ROOT)}: calendar weather must use collapsable section wrapper"
            )

    js_path = ROOT / "static" / "js" / "_pages" / "components__header_weather_widget.js"
    if js_path.is_file() and "isCompact" not in _read(js_path):
        failures.append("header weather JS missing compact toolbar mode")

    result = {
        "status": "pass" if not failures else "fail",
        "finding_count": len(failures),
        "failures": failures,
    }
    if args.write:
        out = ROOT / "docs" / "generated" / "dashboard_datetime_weather_layout_audit.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")

    if failures:
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            for msg in failures:
                print(f"FAIL: {msg}", file=sys.stderr)
        return 1

    print("DASHBOARD_DATETIME_WEATHER_LAYOUT_PASS")
    if args.json:
        print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
