"""Footer surface contract — operator civic vs tenant vs marketing full."""

from pathlib import Path

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_does_not_wire,
    assert_markup,
    assert_wires,
)

ROOT = Path(__file__).resolve().parents[3]

SKELETON = ROOT / "templates/control_plane_skeleton.html"
CIVIC = ROOT / "templates/partials/rmc_operator_footer_civic.html"
COMPACT = ROOT / "templates/partials/rmc_operator_footer_compact.html"
ADMIN_BASE = ROOT / "templates/admin/base.html"
PORTAL_BASE = ROOT / "templates/portal_base.html"
BASE = ROOT / "templates/base.html"
DASHBOARD_FOOTER = ROOT / "templates/components/dashboard_footer.html"


class FooterSurfaceContractTests(SimpleTestCase):
    def test_control_plane_uses_civic_operator_footer(self):
        text = Path("templates/control_plane_skeleton.html").read_text(encoding="utf-8")
        civic = Path("templates/partials/rmc_operator_footer_civic.html").read_text(
            encoding="utf-8"
        )
        assert_wires(self, SKELETON, "rmc_operator_footer_civic.html")
        assert_markup(self, CIVIC, 'data-rmc-footer-surface="operator-civic"')
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
        assert_wires(self, ADMIN_BASE, "control_plane_unified_header.html")
        self.assertIn("control_plane_unified_header.html", admin_base)
        self.assertIn("is_manager_host", admin_base)
        self.assertNotIn("corporate_footer_bundle.html", admin_base)

    def test_portal_never_includes_marketing_footer(self):
        text = Path("templates/portal_base.html").read_text(encoding="utf-8")
        self.assertNotIn("corporate_footer_bundle.html", text)
        self.assertNotIn("marketing_footer.html", text)
        self.assertIn("PORTAL_FOOTER_PARTIAL", text)
        self.assertIn("rmc-footer-surfaces.css", text)
        assert_wires(
            self,
            PORTAL_BASE,
            "rmc_operator_footer_civic.html",
            "control_plane_unified_header.html",
        )
        self.assertIn("SHOW_MANAGER_CORPORATE_FOOTER", text)

    def test_base_manager_login_uses_civic_not_bundle(self):
        assert_wires(self, BASE, "rmc_operator_footer_civic.html")
        assert_does_not_wire(self, BASE, "corporate_footer_bundle.html")

    def test_tenant_dashboard_footer_surface_marker(self):
        assert_markup(
            self, DASHBOARD_FOOTER, 'data-rmc-footer-surface="tenant-standard"'
        )

    def test_operator_footer_uses_preview_cp_footer_layout(self):
        assert_markup(
            self,
            COMPACT,
            "cp-footer-inner",
            "cp-footer-ribbon--primary",
            "rmc-civic-footer__social",
        )
