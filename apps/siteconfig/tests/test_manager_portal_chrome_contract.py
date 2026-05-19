"""Manager corporate footer + tenant portal chrome template contracts."""

from pathlib import Path

from django.test import SimpleTestCase


class ManagerPortalChromeContractTests(SimpleTestCase):
    def test_control_plane_skeleton_wires_compact_operator_footer(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        self.assertIn("SHOW_MANAGER_CORPORATE_FOOTER", text)
        self.assertIn("cp-corporate-footer", text)
        self.assertIn("rmc_operator_footer_compact.html", text)
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertIn("cp_shell_page", text)
        self.assertIn("cp_shell_footer", text)
        self.assertIn("cp-shell-content--with-public-footer", text)
        self.assertIn("rmc-footer-surfaces.css", text)

    def test_control_plane_base_uses_skeleton_shell_blocks(self):
        text = Path("templates/control_plane_base.html").read_text(encoding="utf-8")
        self.assertIn("block cp_shell_page", text)
        self.assertIn("block cp_shell_after", text)
        self.assertNotIn("cp-corporate-footer", text)

    def test_manager_admin_shell_includes_operator_footer(self):
        text = Path("templates/admin/base.html").read_text(encoding="utf-8")
        self.assertIn("is_manager_host", text)
        self.assertIn("rmc_operator_footer_compact.html", text)
        self.assertIn("cp-corporate-footer", text)

    def test_portal_base_excludes_marketing_corporate_footer(self):
        text = Path("templates/portal_base.html").read_text(encoding="utf-8")
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertNotIn("marketing_footer.html", text)
        self.assertIn("PORTAL_FOOTER_PARTIAL", text)
