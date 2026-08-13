#!/usr/bin/env python3
"""Fail-closed platform contract for the shared authenticated Account Center."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    menu = read("templates/components/user_account_center_menu.html")
    owner = read("templates/components/user_dropdown.html")
    admin = read("templates/components/admin_nav_bridge.html")
    css = read("static/css/rmc-user-account-center.css")
    js = read("static/js/rmc-user-account-center.js")
    admin_sidebars = "\n".join(
        (read("templates/admin/sidebar_inner.html"), read("templates/unfold/helpers/navigation.html"))
    )
    shells = "\n".join(
        read(path)
        for path in (
            "templates/base.html",
            "templates/portal_base.html",
            "templates/control_plane_skeleton.html",
            "templates/admin/base_site.html",
        )
    )
    required = {
        "canonical mount": (owner, "user_account_center_menu.html"),
        "legacy non-rendering": (owner, 'data-rmc-account-center-legacy="1"'),
        "tenant admin integration": (admin, 'include "components/user_dropdown.html"'),
        "four-shell asset": (shells, "rmc-user-account-center.css"),
        "identity": (menu, "rmc-account-center__identity"),
        "recommendation": (menu, "rmc-account-center__recommendation"),
        "security": (menu, "accounts:mfa_setup"),
        "normal logout": (menu, 'data-rmc-nav-logout="1"'),
        "shared device logout": (menu, "forget_device=1"),
        "admin return": (menu, "Return to control plane"),
        "offline state": (js, 'addEventListener("offline"'),
        "copilot collision detection": (js, '[data-rmc-copilot-rail]'),
        "viewport positioning": (css, 'data-rmc-account-viewport-positioned="1"'),
        "professional CSS": (css, ".rmc-account-center__primary"),
        "responsive CSS": (css, "@media(max-width:36rem)"),
        "reduced motion": (css, "prefers-reduced-motion"),
    }
    failures = [
        f"missing {label}: {token}"
        for label, (body, token) in required.items()
        if token not in body
    ]
    if shells.count("rmc-user-account-center.css") != 4:
        failures.append("Account Center CSS is not mounted exactly once in all four base shells")
    if "request.user.email }}" in menu:
        failures.append("raw email must not be rendered as visible Account Center identity")
    if 'include "unfold/helpers/navigation_user.html"' in admin_sidebars:
        failures.append("admin sidebar must not render a duplicate user profile control")
    if failures:
        print("USER_ACCOUNT_CENTER_FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("USER_ACCOUNT_CENTER_PASS")
    print("surfaces=tenant,operator,tenant-admin,operator-admin privacy=fail-closed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
