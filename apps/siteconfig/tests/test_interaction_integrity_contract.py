"""Mechanical contracts for platform-wide interaction integrity."""

from pathlib import Path

from django.test import SimpleTestCase

ROOT = Path(__file__).resolve().parents[3]


class InteractionIntegrityContractTests(SimpleTestCase):
    def test_interaction_guard_on_all_shells(self):
        shells = [
            "templates/control_plane_skeleton.html",
            "templates/portal_base.html",
            "templates/base.html",
            "templates/marketing/base_marketing.html",
            "templates/admin/base_site.html",
        ]
        for rel in shells:
            text = (ROOT / rel).read_text(encoding="utf-8")
            wired = "rmc-interaction-guard.js" in text or "rmc_interaction_shell_scripts.html" in text
            self.assertTrue(wired, rel)

    def test_user_dropdown_logout_present(self):
        text = (ROOT / "templates/components/user_dropdown.html").read_text(encoding="utf-8")
        self.assertIn("accounts:logout", text)
        self.assertIn("dropdown-menu-end", text)
        self.assertNotIn('href="#"', text)

    def test_permission_matrix_denied_banner(self):
        text = (ROOT / "templates/siteconfig/permission_matrix_simulator.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("rmc-perm-sim-denied", text)
        js = (ROOT / "static/js/rmc-permission-matrix-simulator.js").read_text(encoding="utf-8")
        self.assertIn("showDenied", js)

    def test_error_templates_include_503(self):
        for rel in (
            "templates/errors/503.html",
            "templates/errors/503_control_plane.html",
        ):
            self.assertTrue((ROOT / rel).is_file(), rel)

    def test_handler503_exported(self):
        from config.urls import handler503, service_unavailable

        self.assertIs(handler503, service_unavailable)

    def test_manager_header_account_allowlist(self):
        from apps.schools.middleware import MANAGER_HOST_ALLOWED_PREFIXES

        for path in (
            "/authentication/documentation/",
            "/authentication/notifications/",
            "/kb/",
        ):
            self.assertTrue(
                any(path.startswith(p) for p in MANAGER_HOST_ALLOWED_PREFIXES),
                path,
            )

    def test_manager_header_css_control_height(self):
        css = (ROOT / "static/css/rmc-platform-header.css").read_text(encoding="utf-8")
        self.assertIn("--rmc-header-control-height", css)
        self.assertIn(".cp-navbar .user-dropdown-trigger", css)

    def test_user_dropdown_points_to_help_surfaces(self):
        text = (ROOT / "templates/components/user_dropdown.html").read_text(encoding="utf-8")
        self.assertIn("manager_help_center", text)
        self.assertIn("kb:kb_home", text)

    def test_manager_admin_footer_wired(self):
        admin_base = (ROOT / "templates/admin/base.html").read_text(encoding="utf-8")
        self.assertIn("rmc_operator_footer_compact.html", admin_base)
        self.assertIn("is_manager_host", admin_base)

    def test_tenant_handler503_matches_root(self):
        from config.tenant_urls import handler503 as tenant_handler503
        from config.urls import service_unavailable

        self.assertIs(tenant_handler503, service_unavailable)
