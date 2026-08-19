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
            "/assist-dock/context.json",
            "/platform-runtime/workflow-progress/stream/",
        ):
            self.assertTrue(
                any(path.startswith(p) for p in MANAGER_HOST_ALLOWED_PREFIXES),
                path,
            )

    def test_manager_header_css_control_height(self):
        css = (ROOT / "static/css/rmc-platform-header.css").read_text(encoding="utf-8")
        self.assertIn("--rmc-header-control-height", css)
        self.assertIn(".cp-navbar .user-dropdown-trigger", css)

    def test_user_dropdown_defers_help_to_tools_rail(self):
        # Platform Clean Header Approval v2 (user-approved SOT batch 1791-1792):
        # Help is a first-class Tools-rail item, NOT a user-dropdown link. The header
        # utilities contract (scripts/verify_header_utilities_contract.py) forbids
        # help-center links in the user dropdown; this test locks the same v2 direction
        # so the two gates cannot contradict each other. Supersedes the prior
        # test_user_dropdown_points_to_help_surfaces assertion.
        text = (ROOT / "templates/components/user_dropdown.html").read_text(encoding="utf-8")
        self.assertNotIn("manager_help_center", text)
        self.assertNotIn("feedback:help_center", text)
        self.assertNotIn("helpUrl", text)
        # Help lives on the shared Tools-rail help panel instead.
        help_panel = (ROOT / "templates/partials/rmc_tools_help_panel.html").read_text(
            encoding="utf-8"
        )
        self.assertIn('trans "Ask Copilot"', help_panel)
        self.assertIn('trans "Contact support"', help_panel)

    def test_tenant_sidebar_points_to_help_center_not_kb_only(self):
        text = (ROOT / "templates/partials/portal_sidebar.html").read_text(encoding="utf-8")
        self.assertIn("feedback:help_center", text)

    def test_manager_admin_workbench_delegates_footer_to_control_plane(self):
        # v15/parity contract: the /admin/ model workbench delegates the civic
        # footer to the control-plane surfaces (see the rationale comment in
        # templates/admin/base.html). The civic partial still carries its surface
        # marker; the workbench adopts the manager control-plane header, not the
        # viewport-pinned civic footer.
        admin_base = (ROOT / "templates/admin/base.html").read_text(encoding="utf-8")
        civic = (ROOT / "templates/partials/rmc_operator_footer_civic.html").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("rmc_operator_footer_civic.html", admin_base)
        self.assertIn('data-rmc-footer-surface="operator-civic"', civic)
        self.assertIn("is_manager_host", admin_base)

    def test_tenant_handler503_matches_root(self):
        from config.tenant_urls import handler503 as tenant_handler503
        from config.urls import service_unavailable

        self.assertIs(tenant_handler503, service_unavailable)

    def test_tenant_urlconf_includes_feedback_help_center(self):
        from django.urls import reverse

        path = reverse("feedback:help_center", urlconf="config.tenant_urls")
        self.assertTrue(path.endswith("/help/") or "/help/" in path)

    def test_tenant_urlconf_includes_feedback_namespace(self):
        text = (ROOT / "config/tenant_urls.py").read_text(encoding="utf-8")
        self.assertTrue(
            'include(("apps.feedback.urls", "feedback")' in text
            or 'include(("apps.feedback.tenant_urls", "feedback")' in text,
            "tenant urlconf must mount feedback help center namespace",
        )
        self.assertIn('namespace="feedback"', text)

    def test_tenant_school_templates_use_marketing_public_find_school(self):
        for rel in (
            "templates/schools/global_login_discovery.html",
            "templates/schools/public_support_hub.html",
            "templates/schools/public_verify_hub.html",
            "templates/schools/partials/school_finder_bento.html",
        ):
            text = (ROOT / rel).read_text(encoding="utf-8")
            self.assertIn("marketing_public_href", text, rel)
            self.assertNotIn("{% url 'find_school' %}", text, rel)
