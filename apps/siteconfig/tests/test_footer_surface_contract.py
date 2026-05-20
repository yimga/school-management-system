"""Footer surface contract — operator compact vs tenant vs marketing full."""

from pathlib import Path

from django.test import SimpleTestCase


class FooterSurfaceContractTests(SimpleTestCase):
    def test_control_plane_uses_compact_operator_footer(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        self.assertIn("rmc_operator_footer_compact.html", text)
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertNotIn("mkt-footer-command", text)

    def test_manager_admin_uses_compact_operator_footer(self):
        admin_base = Path("templates/admin/base.html").read_text(encoding="utf-8")
        admin_site = Path("templates/admin/base_site.html").read_text(encoding="utf-8")
        self.assertIn("rmc_operator_footer_compact.html", admin_base)
        self.assertIn('data-rmc-footer-surface="operator-compact"', admin_base)
        self.assertIn("is_manager_host", admin_base)
        self.assertIn("rmc-footer-surfaces.css", admin_site)
        self.assertNotIn("corporate_footer_bundle.html", admin_base)

    def test_portal_never_includes_marketing_footer(self):
        text = Path("templates/portal_base.html").read_text(encoding="utf-8")
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertNotIn("marketing_footer.html", text)
        self.assertIn("PORTAL_FOOTER_PARTIAL", text)
        self.assertIn("rmc-footer-surfaces.css", text)
        self.assertIn("rmc_operator_footer_compact.html", text)
        self.assertIn("SHOW_MANAGER_CORPORATE_FOOTER", text)

    def test_base_manager_login_uses_compact_not_bundle(self):
        text = Path("templates/base.html").read_text(encoding="utf-8")
        self.assertIn("rmc_operator_footer_compact.html", text)
        self.assertNotIn("corporate_footer_bundle.html", text)

    def test_tenant_dashboard_footer_surface_marker(self):
        text = Path("templates/components/dashboard_footer.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-rmc-footer-surface="tenant-standard"', text)

    def test_base_html_loads_footer_surface_css_for_tenant_guard(self):
        text = Path("templates/base.html").read_text(encoding="utf-8")
        self.assertIn("rmc-footer-surfaces.css", text)
