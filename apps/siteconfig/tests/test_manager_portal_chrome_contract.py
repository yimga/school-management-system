"""Manager corporate footer + tenant portal chrome template contracts."""

from pathlib import Path

from django.test import SimpleTestCase


class ManagerPortalChromeContractTests(SimpleTestCase):
    def test_control_plane_skeleton_wires_corporate_footer(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        self.assertIn("SHOW_MANAGER_CORPORATE_FOOTER", text)
        self.assertIn("cp-corporate-footer", text)
        self.assertIn("corporate_footer_bundle.html", text)
        self.assertIn("data-rmc-manager-corporate-footer", text)
        self.assertIn("manager_corporate_footer", text)

    def test_portal_base_excludes_marketing_corporate_footer(self):
        text = Path("templates/portal_base.html").read_text(encoding="utf-8")
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertNotIn("marketing_footer.html", text)
        self.assertIn("PORTAL_FOOTER_PARTIAL", text)
