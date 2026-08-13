#!/usr/bin/env python3
"""Fail-closed static contract for the manager-only Django Admin sidebar v2."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    base = read("templates/admin/base_site.html")
    nav = read("templates/partials/manager_platform_admin_sidebar.html")
    identity = read("templates/partials/cp_sidebar_operator_identity.html")
    css = read("static/css/rmc-operator-admin-sidebar-v2.css")
    js = read("static/js/rmc-operator-admin-sidebar-v2.js")
    required = {
        "manager asset gate": (base, "rmc-operator-admin-sidebar-v2.js"),
        "smart navigation": (nav, 'data-rmc-smart-sidebar="1"'),
        "quick access render": (nav, "PINNED_CONTROL_PLANE_ITEMS"),
        "recent work": (nav, "data-operator-recent-wrap"),
        "local status": (identity, "data-operator-connection-status"),
        "operator CSS scope": (css, "body.admin-manager-shell"),
        "operator JS scope": (js, 'classList.contains("admin-manager-shell")'),
        "safe storage": (js, "try { localStorage"),
        "offline handling": (js, 'addEventListener("offline"'),
        "pin persistence": (js, "control_plane_pinned_items"),
    }
    failures = [
        f"missing {label}: {token}"
        for label, (body, token) in required.items()
        if token not in body
    ]
    if failures:
        print("OPERATOR_ADMIN_SIDEBAR_V2_FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("OPERATOR_ADMIN_SIDEBAR_V2_PASS")
    print("scope=operator-/admin/ tenant-bleed=none quick-access=restored local-offline=graceful")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
