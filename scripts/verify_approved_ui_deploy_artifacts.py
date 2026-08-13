#!/usr/bin/env python3
"""Fail deployment when approved sidebar/Account Center assets cannot render."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATIC_ROOT = ROOT / "staticfiles"

ASSETS = (
    "css/rmc-governed-outcome.css",
    "css/rmc-tenant-admin-sidebar-v2.css",
    "js/rmc-tenant-admin-sidebar-v2.js",
    "css/rmc-operator-admin-sidebar-v2.css",
    "js/rmc-operator-admin-sidebar-v2.js",
    "css/rmc-user-account-center.css",
    "js/rmc-user-account-center.js",
    "css/rmc-tenant-dashboard-balance.css",
)


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def verify_source(failures: list[str]) -> None:
    for asset in ASSETS:
        source = ROOT / "static" / asset
        if not source.is_file() or source.stat().st_size < 100:
            failures.append(f"missing or empty source asset: static/{asset}")

    base = read("templates/admin/base_site.html")
    account_owner = read("templates/components/user_dropdown.html")
    admin_bridge = read("templates/components/admin_nav_bridge.html")
    sw = read("static/js/service-worker.js")
    for asset in ASSETS:
        if f'"/static/{asset}"' not in sw:
            failures.append(f"service worker does not update approved asset: {asset}")
    for token in (
        "rmc-tenant-admin-sidebar-v2.css",
        "rmc-operator-admin-sidebar-v2.css",
        "rmc-user-account-center.css",
    ):
        if token not in base:
            failures.append(f"admin base does not mount: {token}")
    if "user_account_center_menu.html" not in account_owner:
        failures.append("canonical user dropdown does not mount Account Center")
    if 'include "components/user_dropdown.html"' not in admin_bridge:
        failures.append("tenant admin does not mount canonical user dropdown")
    if "sms-v4.06.40-governed-outcome-surfaces" not in sw:
        failures.append("service-worker cache version was not advanced for approved UI")
    if "rmc-service-worker-registration.js" not in base or "rmc-service-worker-url" not in base:
        failures.append("admin shell cannot update a root-scope service worker")
    registration = read("static/js/rmc-service-worker-registration.js")
    if 'data-rmc-shell-root="django-admin"' not in registration:
        failures.append("service-worker registration does not recognize admin shell")


def verify_staticfiles(failures: list[str]) -> None:
    manifest_path = STATIC_ROOT / "staticfiles.json"
    if not manifest_path.is_file():
        failures.append("collectstatic manifest missing: staticfiles/staticfiles.json")
        return
    try:
        paths = json.loads(manifest_path.read_text(encoding="utf-8"))["paths"]
    except (json.JSONDecodeError, KeyError) as exc:
        failures.append(f"invalid collectstatic manifest: {exc}")
        return
    for asset in ASSETS:
        hashed = paths.get(asset)
        if not hashed:
            failures.append(f"manifest has no hashed mapping: {asset}")
            continue
        output = STATIC_ROOT / hashed
        if not output.is_file() or output.stat().st_size < 100:
            failures.append(f"hashed artifact missing or empty: {hashed}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--staticfiles", action="store_true")
    args = parser.parse_args()
    failures: list[str] = []
    verify_source(failures)
    if args.staticfiles:
        verify_staticfiles(failures)
    if failures:
        print("APPROVED_UI_DEPLOY_ARTIFACTS_FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("APPROVED_UI_DEPLOY_ARTIFACTS_PASS")
    print(f"assets={len(ASSETS)} staticfiles={'verified' if args.staticfiles else 'not-requested'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
