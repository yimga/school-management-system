from pathlib import Path
from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]
class OperatorAdminSidebarV2Tests(SimpleTestCase):
    def test_assets_are_manager_host_gated(self):
        base=(ROOT/"templates/admin/base_site.html").read_text(encoding="utf-8")
        self.assertIn("rmc-operator-admin-sidebar-v2.css",base)
        self.assertIn("rmc-operator-admin-sidebar-v2.js",base)
        self.assertIn("{% if is_manager_host %}",base)
    def test_operator_sidebar_has_intelligence_quick_access_recent_and_status(self):
        nav=(ROOT/"templates/partials/manager_platform_admin_sidebar.html").read_text(encoding="utf-8")
        identity=(ROOT/"templates/partials/cp_sidebar_operator_identity.html").read_text(encoding="utf-8")
        for token in ('data-rmc-smart-sidebar="1"',"PINNED_CONTROL_PLANE_ITEMS","data-operator-recent-wrap"):
            self.assertIn(token,nav)
        self.assertIn("data-operator-connection-status",identity)
    def test_runtime_is_operator_scoped_and_offline_safe(self):
        js=(ROOT/"static/js/rmc-operator-admin-sidebar-v2.js").read_text(encoding="utf-8")
        self.assertIn('classList.contains("admin-manager-shell")',js)
        self.assertIn('addEventListener("offline"',js)
        self.assertIn("control_plane_pinned_items",js)
