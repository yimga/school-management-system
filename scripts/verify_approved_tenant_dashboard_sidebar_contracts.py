#!/usr/bin/env python3
"""Fail-closed parity contract for the three approved tenant/admin previews."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8", errors="replace")


def main() -> int:
    tenant_nav = read("templates/admin/sidebar_inner.html") + read("templates/admin/app_list.html")
    tenant_js = read("static/js/rmc-tenant-admin-sidebar-v2.js")
    operator_nav = read("templates/partials/manager_platform_admin_sidebar.html")
    operator_context = read("templates/partials/cp_sidebar_operator_identity.html")
    operator_js = read("static/js/rmc-operator-admin-sidebar-v2.js")
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
        "tenant context": (tenant_nav, "rmc-tenant-admin-sidebar-context"),
        "tenant search": (tenant_nav, "rmcTenantAdminNavSearch"),
        "tenant pins": (tenant_nav, "admin-sidebar-pinned-list"),
        "tenant recents": (tenant_nav, "data-rmc-admin-recent-wrap"),
        "tenant setup zone": (tenant_nav, "School setup"),
        "tenant offline": (tenant_js, 'addEventListener("offline"'),
        "tenant keyboard": (tenant_js, "function focusables"),
        "operator context": (operator_context, "data-rmc-sidebar-workspace-context"),
        "operator connectivity": (operator_context, "data-operator-connection-status"),
        "operator search": (operator_nav, "rmcOperatorAdminNavSearch"),
        "operator quick access": (operator_nav, "PINNED_CONTROL_PLANE_ITEMS"),
        "operator recents": (operator_nav, "data-operator-recent-wrap"),
        "operator keyboard": (operator_js, "function focusables"),
        "operator offline": (operator_js, 'addEventListener("offline"'),
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
