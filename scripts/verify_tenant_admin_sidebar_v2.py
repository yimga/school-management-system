#!/usr/bin/env python3
"""Static fail-closed contract for the tenant-only Django Admin sidebar v2."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    failures: list[str] = []
    base = read("templates/admin/base_site.html")
    inner = read("templates/admin/sidebar_inner.html")
    apps = read("templates/admin/app_list.html")
    css = read("static/css/rmc-tenant-admin-sidebar-v2.css")
    js = read("static/js/rmc-tenant-admin-sidebar-v2.js")
    required = {
        "tenant conditional": (base, "{% if not is_manager_host %}<link"),
        "tenant shell guard": (js, 'closest(\'[data-rmc-app-shell-host="tenant"]\')'),
        "CSS tenant root": (css, '[data-rmc-app-shell-host="tenant"]'),
        "search": (inner, "rmcTenantAdminNavSearch"),
        "connectivity": (inner, "data-rmc-admin-connectivity"),
        "pinned empty": (apps, "data-rmc-pinned-empty"),
        "recent": (apps, "data-rmc-admin-recent-wrap"),
        "safe storage": (js, "safeRead"),
        "dynamic keyboard": (js, "function focusables"),
        "offline events": (js, 'addEventListener("offline"'),
    }
    for label, (body, token) in required.items():
        if token not in body:
            failures.append(f"missing {label}: {token}")
    if "is_manager_host" not in base or "rmc-tenant-admin-sidebar-v2.js" not in base:
        failures.append("sidebar assets are not host-gated")
    if 'include "unfold/helpers/navigation_user.html"' in inner:
        failures.append("tenant admin sidebar duplicates the header Account Center")
    if failures:
        print("TENANT_ADMIN_SIDEBAR_V2_FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("TENANT_ADMIN_SIDEBAR_V2_PASS")
    print("scope=tenant-/admin/ operator-bleed=none local-offline=graceful")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
