"""Footer surface contract — operator civic vs tenant vs marketing full."""

from pathlib import Path

from django.test import SimpleTestCase


class FooterSurfaceContractTests(SimpleTestCase):
    def test_control_plane_uses_civic_operator_footer(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        civic = Path("templates/partials/rmc_operator_footer_civic.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc_operator_footer_civic.html", text)
        self.assertIn('data-rmc-footer-surface="operator-civic"', civic)
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertNotIn("mkt-footer-command", text)

    def test_manager_admin_workbench_delegates_footer_to_control_plane(self):
        # v15/parity contract (2026-07-20 "Repair operator and tenant Django admin
        # parity"): the /admin/ MODEL WORKBENCH deliberately does NOT carry the
        # viewport-pinned civic footer (nor the footer-surfaces CSS) — those belong
        # to the control-plane surfaces (control_plane_skeleton / portal_base /
        # base), not the Django model workbench. See the rationale comment in
        # templates/admin/base.html. The workbench still adopts the control-plane
        # unified header on the manager host and never the marketing corporate bundle.
        admin_base = Path("templates/admin/base.html").read_text(encoding="utf-8")
        self.assertNotIn("rmc_operator_footer_civic.html", admin_base)
        self.assertIn("control_plane_unified_header.html", admin_base)
        self.assertIn("is_manager_host", admin_base)
        self.assertNotIn("corporate_footer_bundle.html", admin_base)

    def test_portal_never_includes_marketing_footer(self):
        text = Path("templates/portal_base.html").read_text(encoding="utf-8")
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertNotIn("marketing_footer.html", text)
        self.assertIn("PORTAL_FOOTER_PARTIAL", text)
        self.assertIn("rmc-footer-surfaces.css", text)
        self.assertIn("rmc_operator_footer_civic.html", text)
        self.assertIn("control_plane_unified_header.html", text)
        self.assertIn("SHOW_MANAGER_CORPORATE_FOOTER", text)

    def test_base_manager_login_uses_civic_not_bundle(self):
        text = Path("templates/base.html").read_text(encoding="utf-8")
        self.assertIn("rmc_operator_footer_civic.html", text)
        self.assertNotIn("corporate_footer_bundle.html", text)

    def test_tenant_dashboard_footer_surface_marker(self):
        text = Path("templates/components/dashboard_footer.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('data-rmc-footer-surface="tenant-standard"', text)

    def test_operator_footer_uses_preview_cp_footer_layout(self):
        text = Path("templates/partials/rmc_operator_footer_compact.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("cp-footer-inner", text)
        self.assertIn("cp-footer-ribbon--primary", text)
        self.assertIn("rmc-civic-footer__social", text)
