"""Verify the platform-wide quiet-header and Tools-owned Help contract."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def require(text: str, needle: str, source: str, findings: list[str]) -> None:
    if needle not in text:
        findings.append(f"{source}: missing {needle!r}")


def forbid(text: str, needle: str, source: str, findings: list[str]) -> None:
    if needle in text:
        findings.append(f"{source}: forbidden legacy contract {needle!r}")


def main() -> int:
    findings: list[str] = []
    tenant_nav_path = "templates/partials/tenant_primary_nav.html"
    operator_nav_path = "templates/partials/control_plane_primary_nav.html"
    tenant_util_path = "templates/components/rmc_tenant_header_utilities.html"
    operator_util_path = "templates/components/rmc_operator_workspace_dropdown.html"
    portal_path = "templates/portal_base.html"
    admin_path = "templates/components/admin_nav_bridge.html"
    tenant_tools_path = "templates/partials/rmc_tenant_tools_page_data.html"
    operator_tools_path = "templates/partials/rmc_operator_tools_page_data.html"
    user_dropdown_path = "templates/components/user_dropdown.html"
    dashboard_footer_path = "templates/components/dashboard_footer.html"

    tenant_nav = read(tenant_nav_path)
    operator_nav = read(operator_nav_path)
    tenant_util = read(tenant_util_path)
    operator_util = read(operator_util_path)
    portal = read(portal_path)
    admin = read(admin_path)
    tenant_tools = read(tenant_tools_path)
    operator_tools = read(operator_tools_path)
    user_dropdown = read(user_dropdown_path)
    dashboard_footer = read(dashboard_footer_path)

    for text, source in ((tenant_nav, tenant_nav_path), (operator_nav, operator_nav_path)):
        forbid(text, 'trans "More"', source, findings)
        forbid(text, "data-rmc-cp-nav-more", source, findings)

    require(tenant_nav, "data-rmc-quiet-header", tenant_nav_path, findings)
    require(operator_nav, "forloop.counter <= 2", operator_nav_path, findings)
    require(tenant_util, 'trans "Utilities"', tenant_util_path, findings)
    require(operator_util, 'trans "Utilities"', operator_util_path, findings)
    require(tenant_util, "siteconfig:sync_center", tenant_util_path, findings)
    forbid(tenant_util, "feedback:help_center", tenant_util_path, findings)
    forbid(operator_util, "manager_help_center", operator_util_path, findings)
    require(portal, 'include "components/rmc_tenant_header_utilities.html"', portal_path, findings)
    require(admin, 'include "components/rmc_tenant_header_utilities.html"', admin_path, findings)
    require(admin, "admin-nav-bridge__home-btn", admin_path, findings)
    require(admin, "portal_home_url", admin_path, findings)
    require(tenant_tools, '"page": ["help"', tenant_tools_path, findings)
    require(operator_tools, '"page": ["help"', operator_tools_path, findings)
    require(portal, "if not request.user.is_authenticated", portal_path, findings)
    forbid(user_dropdown, "helpUrl", user_dropdown_path, findings)
    forbid(user_dropdown, "manager_help_center", user_dropdown_path, findings)
    forbid(user_dropdown, "feedback:help_center", user_dropdown_path, findings)
    forbid(dashboard_footer, "feedback:help_center", dashboard_footer_path, findings)

    for text, source in ((tenant_tools, tenant_tools_path), (operator_tools, operator_tools_path)):
        forbid(text, "tools.enabled|default:False", source, findings)
        require(text, 'trans "Tools" as rmc_tools_label', source, findings)
        require(text, '"tab_label": "{{ rmc_tools_label|escapejs }}"', source, findings)

    if findings:
        print("Header utilities contract: FAIL")
        for finding in findings:
            print(f"- {finding}")
        return 1
    print("Header utilities contract: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
