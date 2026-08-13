from pathlib import Path
from django.test import SimpleTestCase

ROOT=Path(__file__).resolve().parents[3]
class TenantAdminSidebarV2Tests(SimpleTestCase):
    def test_assets_are_tenant_host_gated(self):
        base=(ROOT/"templates/admin/base_site.html").read_text(encoding="utf-8")
        self.assertIn('{% if not is_manager_host %}<link rel="stylesheet"',base)
        self.assertIn("rmc-tenant-admin-sidebar-v2.js",base)
    def test_operator_shell_is_not_a_sidebar_v2_mount(self):
        base=(ROOT/"templates/admin/base.html").read_text(encoding="utf-8")
        self.assertIn('data-rmc-app-shell-host="{% if is_manager_host %}manager{% else %}tenant{% endif %}"',base)
        js=(ROOT/"static/js/rmc-tenant-admin-sidebar-v2.js").read_text(encoding="utf-8")
        self.assertIn('closest(\'[data-rmc-app-shell-host="tenant"]\')',js)
    def test_sidebar_has_search_recent_pinned_and_connectivity_contracts(self):
        content="\n".join((ROOT/path).read_text(encoding="utf-8") for path in ("templates/admin/sidebar_inner.html","templates/admin/app_list.html"))
        for token in ("rmcTenantAdminNavSearch","data-rmc-admin-recent-wrap","data-rmc-pinned-empty","data-rmc-admin-connectivity"):
            self.assertIn(token,content)
