"""Mechanical contracts for platform-wide interaction integrity."""

from pathlib import Path
from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.siteconfig.tests._template_nodes import (
    assert_markup,
    rendered_source,
)

ROOT = Path(__file__).resolve().parents[3]

USER_DROPDOWN = ROOT / "templates/components/user_dropdown.html"
PERMISSION_MATRIX = ROOT / "templates/siteconfig/permission_matrix_simulator.html"
PORTAL_SIDEBAR = ROOT / "templates/partials/portal_sidebar.html"
TOOLS_HELP_PANEL = ROOT / "templates/partials/rmc_tools_help_panel.html"
OPERATOR_FOOTER_CIVIC = ROOT / "templates/partials/rmc_operator_footer_civic.html"


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
        # accounts:logout is a {% url %} argument: it renders to a path, so the
        # route NAME is only ever visible in the source. Same for the negative.
        self.assertIn("accounts:logout", text)
        self.assertNotIn('href="#"', text)
        # The menu class is markup, so ask the engine whether it is EMITTED --
        # a needle sitting inside {% comment %} is not on the page.
        assert_markup(self, USER_DROPDOWN, "dropdown-menu-end")

    def test_permission_matrix_denied_banner(self):
        assert_markup(self, PERMISSION_MATRIX, "rmc-perm-sim-denied")
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
        # Those two reads cannot tell a live panel from one wrapped in
        # {% comment %}: the bytes are the same either way. The panel is behind
        # an is_authenticated guard, so render it FROM ITS BYTES with a signed-in
        # request and read the labels off the output instead.
        signed_in = SimpleNamespace(user=SimpleNamespace(is_authenticated=True))
        panel_html = rendered_source(TOOLS_HELP_PANEL, {"request": signed_in})
        self.assertIn("Ask Copilot", panel_html)
        self.assertIn("Contact support", panel_html)
        assert_markup(
            self,
            TOOLS_HELP_PANEL,
            "data-rmc-tools-help-copilot",
            "data-rmc-tools-help-support",
        )

    def test_tenant_sidebar_points_to_help_center_not_kb_only(self):
        text = (ROOT / "templates/partials/portal_sidebar.html").read_text(encoding="utf-8")
        # The route name exists only as a {% url %} argument, so it stays a read.
        self.assertIn("feedback:help_center", text)
        # The sidebar footer that carries that link has to be EMITTED, not merely
        # spelled somewhere in the file.
        assert_markup(
            self, PORTAL_SIDEBAR, "portal-sidebar-footer", "bi-question-circle"
        )

    def test_manager_admin_workbench_delegates_footer_to_control_plane(self):
        # v15/parity contract: the /admin/ model workbench delegates the civic
        # footer to the control-plane surfaces (see the rationale comment in
        # templates/admin/base.html). The civic partial still carries its surface
        # marker; the workbench adopts the manager control-plane header, not the
        # viewport-pinned civic footer.
        admin_base = (ROOT / "templates/admin/base.html").read_text(encoding="utf-8")
        self.assertNotIn("rmc_operator_footer_civic.html", admin_base)
        # is_manager_host is an {% if %} condition -- template code, which no parse
        # and no render can see, so that one stays a source read.
        self.assertIn("is_manager_host", admin_base)
        # The surface marker is markup: ask whether the partial EMITS it.
        assert_markup(
            self, OPERATOR_FOOTER_CIVIC, 'data-rmc-footer-surface="operator-civic"'
        )

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
            # marketing_public_href is a custom TAG and find_school a {% url %}
            # argument: both are template code, invisible to a parse, so both
            # assertions stay reads.
            self.assertIn("marketing_public_href", text, rel)
            self.assertNotIn("{% url 'find_school' %}", text, rel)
            # What a read cannot tell is whether the surface still renders at
            # all. Every one of these four carries the platform critical-read
            # sentinel, and a {% comment %} emits neither.
            assert_markup(
                self,
                ROOT / rel,
                "rmc-empty-state-sentinel",
                'data-page-critical-read="1"',
            )
