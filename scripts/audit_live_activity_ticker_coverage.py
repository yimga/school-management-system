#!/usr/bin/env python3
"""Audit LIVE activity ticker coverage — manager + tenant shells."""

from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REALDATA = ROOT / "apps" / "siteconfig" / "cockpit_activity_ticker_realdata.py"
TICKER_PARTIAL = ROOT / "templates" / "partials" / "cockpit" / "_activity_ticker.html"
HEADER_WEATHER = ROOT / "templates" / "components" / "header_weather_widget.html"
CAL_WEATHER = ROOT / "templates" / "partials" / "cockpit" / "_calendar_weather.html"

MANAGER_SHELLS = [
    ROOT / "templates" / "control_plane_base.html",
    ROOT / "templates" / "portal_base.html",
    ROOT / "templates" / "admin" / "base.html",
]

TENANT_SHELLS = [
    ROOT / "templates" / "portal_base.html",
    ROOT / "templates" / "base.html",
]

DASHBOARDS_WITH_CAL = [
    ROOT / "templates" / "accounts" / "backend_dashboard.html",
    ROOT / "templates" / "teacher" / "dashboard.html",
    ROOT / "templates" / "parent" / "dashboard.html",
    ROOT / "templates" / "student" / "learning_home.html",
    ROOT / "templates" / "schools" / "super_dashboard.html",
]

REQUIRED_MANAGER_SOURCES = [
    "_source_migration_audit_events",
    "_source_school_provisioning",
    "_source_schools_pending_approval",
    "_source_tenant_subscription_changes",
    "_source_webhook_delivery_failures",
    "_source_migration_run_failures",
    "_source_offboarding_activity",
]

# NOTE: _source_email_delivery_events is TENANT-scoped, not manager. schoolops
# is a TENANT_APPS app, so its table exists only inside tenant schemas; querying
# it from the manager/public schema raises UndefinedTable on every operator page.
REQUIRED_TENANT_SOURCES = [
    "_source_tenant_attendance_milestones",
    "_source_tenant_fee_receipts",
    "_source_tenant_new_enrollments",
    "_source_tenant_communication_activity",
    "_source_email_delivery_events",
]

MIN_MANAGER_SOURCES = 6
MIN_TENANT_SOURCES = 3
MIN_CARDS_CAP = 12


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _fail(messages: list[str]) -> int:
    for msg in messages:
        print(f"FAIL: {msg}", file=sys.stderr)
    return 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []

    realdata_src = _read(REALDATA)
    if "merge_activity_ticker_card_lists" not in realdata_src:
        failures.append("realdata missing merge_activity_ticker_card_lists")
    if "MAX_CARDS_TOTAL = 16" not in realdata_src and "MAX_CARDS_TOTAL = 16," not in realdata_src:
        if "MAX_CARDS_TOTAL = 16" not in realdata_src.replace(" ", ""):
            failures.append("MAX_CARDS_TOTAL should be >= 16 for multi-item LIVE strip")

    for fn in REQUIRED_MANAGER_SOURCES:
        if f"def {fn}" not in realdata_src:
            failures.append(f"manager ticker source missing: {fn}")

    for fn in REQUIRED_TENANT_SOURCES:
        if f"def {fn}" not in realdata_src:
            failures.append(f"tenant ticker source missing: {fn}")

    ticker_html = _read(TICKER_PARTIAL)
    if ticker_html.count("{% for card in cockpit.activity_ticker.cards %}") < 2:
        failures.append("manager ticker partial must duplicate track for seamless scroll")
    if "tenant_activity_ticker.enabled|default_if_none:True" not in ticker_html:
        failures.append("tenant ticker should default enabled when cards exist")

    for shell in MANAGER_SHELLS:
        if shell.exists() and "_activity_ticker.html" not in _read(shell):
            failures.append(f"manager shell missing activity ticker include: {shell.relative_to(ROOT)}")

    header_html = _read(HEADER_WEATHER)
    if "data-local-timezone" not in header_html:
        failures.append("header weather widget missing data-local-timezone")
    if "data-header-datetime-global" not in header_html:
        failures.append("header weather widget missing global time fallback node")

    cal_html = _read(CAL_WEATHER)
    if "data-rmc-cal-weather-now" not in cal_html:
        failures.append("calendar weather partial missing live clock hook")
    if "rmc-calendar-weather-clock.js" not in cal_html:
        failures.append("calendar weather partial missing clock script")

    for dash in DASHBOARDS_WITH_CAL:
        if dash.exists() and "_calendar_weather.html" not in _read(dash):
            failures.append(f"dashboard missing calendar weather include: {dash.relative_to(ROOT)}")

    manager_topbar = ROOT / "templates" / "partials" / "manager_operator_topbar.html"
    if manager_topbar.exists():
        topbar = _read(manager_topbar)
        if "header_weather_widget.html" not in topbar:
            failures.append("manager operator topbar missing header weather widget")
        if "rmc-platform-header__context" not in topbar:
            failures.append("manager topbar missing rmc-platform-header__context slot")

    ctx_src = _read(ROOT / "apps" / "siteconfig" / "cockpit_context.py")
    if "merge_activity_ticker_sections" not in ctx_src:
        failures.append("cockpit_context must merge ticker cards (not replace demo)")

    if failures:
        if args.json:
            import json

            print(json.dumps({"status": "fail", "failures": failures}, indent=2))
        return _fail(failures)

    print("LIVE_ACTIVITY_TICKER_COVERAGE_PASS")
    if args.json:
        import json

        print(
            json.dumps(
                {
                    "status": "pass",
                    "manager_sources": len(REQUIRED_MANAGER_SOURCES),
                    "tenant_sources": len(REQUIRED_TENANT_SOURCES),
                },
                indent=2,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
