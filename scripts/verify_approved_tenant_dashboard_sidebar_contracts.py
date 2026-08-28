#!/usr/bin/env python3
"""Fail-closed parity contract for the three approved tenant/admin previews."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    sidebar_body = read("templates/admin/sidebar_v3_body.html")
    tenant_nav = read("templates/admin/sidebar_inner.html") + sidebar_body
    sidebar_js = read("static/js/rmc-admin-sidebar-v3.js")
    operator_nav = read("templates/partials/manager_platform_admin_sidebar.html") + sidebar_body
    operator_context = read("templates/partials/cp_sidebar_operator_identity.html")
    dashboard = read("templates/accounts/backend_dashboard.html")
    portal_shell = read("templates/portal_base.html")
    dashboard_css = "\n".join(
        read(path)
        for path in (
            "static/css/backend-dashboard-v2.css",
            "static/css/rmc-tenant-dashboard-v2.css",
            "static/css/rmc-tenant-dashboard-100x.css",
            "static/css/rmc-tenant-dashboard-balance.css",
        )
    )
    requirements = {
        "tenant scope": (tenant_nav, 'data-rmc-admin-sidebar-scope="tenant"'),
        "tenant command search": (tenant_nav, "data-rmc-admin-command-open"),
        "tenant pins": (tenant_nav, "data-rmc-admin-pinned-wrap"),
        "tenant recents": (tenant_nav, "data-rmc-admin-recent-wrap"),
        "tenant work areas": (tenant_nav, "data-rmc-admin-work-areas"),
        "sidebar offline queue": (sidebar_js, 'addEventListener("offline"'),
        "sidebar keyboard": (sidebar_js, 'event.key === "ArrowDown"'),
        "operator context": (operator_context, "data-rmc-sidebar-workspace-context"),
        "operator connectivity": (operator_context, "data-operator-connection-status"),
        "operator scope": (operator_nav, 'data-rmc-admin-sidebar-scope="operator"'),
        "operator command search": (operator_nav, "data-rmc-admin-command-open"),
        "operator recents": (operator_nav, "data-rmc-admin-recent-wrap"),
        "sidebar conflict rebase": (sidebar_js, "revision_conflict"),
        "sidebar base revision": (sidebar_js, "expected_revision"),
        "dashboard page owner": (dashboard, 'data-shell-surface="backend-dashboard"'),
        "dashboard role home": (dashboard, 'data-rmc-backend-role-home-panel="1"'),
        "dashboard primary action": (dashboard, 'data-rmc-backend-role-home-primary="1"'),
        "dashboard tenant palette": (dashboard, "--dashboard-theme-primary"),
        "dashboard responsive cards": (dashboard_css, "repeat(auto-fit"),
        "dashboard balanced grid": (dashboard_css, "justify-content: center"),
        "dashboard balance backend mount": (dashboard, "rmc-tenant-dashboard-balance.css"),
        "dashboard balance portal mount": (portal_shell, "rmc-tenant-dashboard-balance.css"),
        "dashboard semantic success": (dashboard_css, "--rmc-dh-accent"),
        "dashboard semantic warning": (dashboard_css, "--rmc-dh-warn"),
        "dashboard semantic danger": (dashboard_css, "--rmc-dh-danger"),
        "dashboard reduced motion": (dashboard_css, "prefers-reduced-motion"),
    }
    failures = [
        f"missing {label}: {token}"
        for label, (body, token) in requirements.items()
        if token not in body
    ]
    duplicate_profile_tokens = (
        "accounts:user_profile",
        "request.user.get_full_name",
        "request.user.username",
        'include "unfold/helpers/navigation_user.html"',
    )
    sidebar_sources = tenant_nav + operator_nav + operator_context
    for token in duplicate_profile_tokens:
        if token in sidebar_sources:
            failures.append(f"sidebar duplicates header-owned profile: {token}")
    if failures:
        print("APPROVED_TENANT_DASHBOARD_SIDEBAR_CONTRACTS_FAIL")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("APPROVED_TENANT_DASHBOARD_SIDEBAR_CONTRACTS_PASS")
    print("contracts=tenant-dashboard,tenant-admin-sidebar,operator-admin-sidebar profile-owner=header")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
