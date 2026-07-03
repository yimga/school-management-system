"""v4.02.1 — Nav sidebar rail + resize contract tests."""

from __future__ import annotations

from django.template import Context, Template
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User
from apps.schools.tests.manager_client import login_manager_control_plane


class NavSidebarCockpitDefaultsTests(SimpleTestCase):
    def test_manager_200x_includes_nav_sidebar_defaults(self) -> None:
        from apps.siteconfig.cockpit_manager_200x import manager_200x_defaults

        payload = manager_200x_defaults()
        nav = payload.get("nav_sidebar")
        self.assertIsInstance(nav, dict)
        self.assertTrue(nav.get("enabled"))
        self.assertEqual(nav.get("default_mode"), "normal")
        self.assertEqual(nav.get("default_width"), 280)
        self.assertEqual(nav.get("min_width"), 200)
        self.assertEqual(nav.get("max_width"), 420)
        self.assertEqual(nav.get("rail_width"), 44)


class NavSidebarShellTemplateTests(SimpleTestCase):
    def test_control_plane_skeleton_wires_nav_sidebar_assets(self) -> None:
        from django.template.loader import get_template

        source = get_template("control_plane_skeleton.html").template.source
        self.assertIn("rmc-nav-sidebar.css", source)
        self.assertIn("rmc-nav-sidebar.js", source)
        self.assertIn("rmc_nav_sidebar_page_data.html", source)
        self.assertIn("rmc-nav-sidebar-host", source)

    def test_control_plane_base_mounts_toolbar_and_col(self) -> None:
        from django.template.loader import get_template

        source = get_template("control_plane_base.html").template.source
        self.assertIn("rmc-nav-sidebar__mount", source)
        self.assertIn("rmc_nav_sidebar_toolbar.html", source)
        self.assertIn('id="cp-sidebar-col"', source)

    def test_admin_manager_sidebar_wires_nav_contract(self) -> None:
        from django.template.loader import get_template

        source = get_template("admin/base.html").template.source
        self.assertIn("rmc-nav-sidebar-host", source)
        self.assertIn("rmc_nav_sidebar_toolbar.html", source)
        self.assertIn("rmc_nav_sidebar_resize_handle.html", source)

    def test_portal_sidebar_retired_duplicate_collapse(self) -> None:
        from django.template.loader import get_template

        source = get_template("partials/portal_sidebar.html").template.source
        self.assertNotIn("portal-sidebar-collapse-wrap", source)

    def test_nav_sidebar_toolbar_places_filter_between_toggle_and_label(self) -> None:
        from django.template.loader import get_template

        source = get_template("partials/rmc_nav_sidebar_toolbar.html").template.source
        toggle_index = source.index("rmc-nav-sidebar__toggle")
        filter_index = source.index("data-rmc-sidebar-filter-input")
        prefs_index = source.index("data-rmc-sidebar-prefs-toggle")
        label_index = source.index("rmc-nav-sidebar__toggle-label")
        self.assertLess(toggle_index, filter_index)
        self.assertLess(filter_index, prefs_index)
        self.assertLess(prefs_index, label_index)
        self.assertNotIn("nav-search", source)

    def test_zero_ticket_shell_uses_nav_sidebar_mount(self) -> None:
        from django.template.loader import get_template

        source = get_template("siteconfig/zero_ticket_shell.html").template.source
        self.assertIn('id="cp-sidebar-col"', source)
        self.assertIn("rmc-nav-sidebar__mount", source)
        self.assertIn("rmc_nav_sidebar_toolbar.html", source)

    def test_control_plane_base_canvas_container(self) -> None:
        from django.template.loader import get_template

        source = get_template("control_plane_base.html").template.source
        self.assertIn("rmc-shell-canvas-container", source)

    def test_portal_base_unified_nav_sidebar(self) -> None:
        from django.template.loader import get_template

        source = get_template("portal_base.html").template.source
        self.assertIn("rmc-nav-sidebar.css", source)
        self.assertIn("rmc-nav-sidebar.js", source)
        self.assertIn("rmc_nav_sidebar_page_data.html", source)
        self.assertIn("rmc-shell-canvas-container", source)
        self.assertNotIn("portal-resize-handle", source)
        self.assertNotIn("portal-resize-keyboard.js", source)

    def test_portal_base_sidebar_integrity_no_bootstrap_width_cols(self) -> None:
        from django.template.loader import get_template

        source = get_template("portal_base.html").template.source
        self.assertNotIn("col-lg-3 col-xl-2", source)
        self.assertNotIn("col-lg-9 col-xl-10", source)
        self.assertNotIn("cp-sidebar-inner cp-sidebar-inner--surface p-2 rounded", source)

    def test_zero_ticket_sidebar_inner_scroll_wrapper(self) -> None:
        from django.template.loader import get_template

        source = get_template("siteconfig/zero_ticket_shell.html").template.source
        self.assertIn(
            'class="cp-sidebar-inner cp-sidebar-inner--surface d-flex flex-column flex-grow-1 min-h-0 p-2"',
            source,
        )

    def test_nav_sidebar_css_integrity_block(self) -> None:
        from pathlib import Path

        css = Path("static/css/rmc-nav-sidebar.css").read_text(encoding="utf-8")
        self.assertIn("Sidebar visual integrity", css)
        self.assertIn("portal-layout-row:has(.rmc-nav-sidebar__mount)", css)
        self.assertIn("grid-template-columns: 2rem minmax(0, 1fr) 2rem auto", css)
        self.assertIn(".rmc-nav-sidebar__filter", css)
        self.assertIn(".rmc-nav-sidebar__prefs", css)
        self.assertIn("#portal-sidebar-col.rmc-nav-sidebar--rail .rmc-nav-sidebar__filter", css)

    def test_manager_control_plane_grid_uses_sidebar_var(self) -> None:
        from pathlib import Path

        css = Path("static/css/manager-control-plane.css").read_text(encoding="utf-8")
        self.assertIn("--portal-sidebar-width", css)
        self.assertNotIn("clamp(16rem, 18vw, 20rem)", css)

    def test_backend_shell_parity_rail_width(self) -> None:
        from pathlib import Path

        css = Path("static/css/backend-shell-parity.css").read_text(encoding="utf-8")
        self.assertIn("--rmc-nav-sidebar-rail-w", css)
        self.assertNotIn("72px !important", css)

    def test_portal_shell_bootstrap_delegates_sidebar(self) -> None:
        from pathlib import Path

        bootstrap = Path("static/js/portal-shell-bootstrap.js").read_text(encoding="utf-8")
        self.assertIn("rmc-nav-sidebar", bootstrap)
        self.assertNotIn("portal-resize-handle", bootstrap)
        self.assertNotIn("portal-sidebar-collapsed", bootstrap)

    def test_nav_sidebar_js_binds_header_filter(self) -> None:
        from pathlib import Path

        source = Path("static/js/rmc-nav-sidebar.js").read_text(encoding="utf-8")
        self.assertIn("bindSidebarFilter(shell)", source)
        self.assertIn("[data-rmc-sidebar-filter-input]", source)
        self.assertIn(".cp-sidebar__item, .nav-link, .admin-sidebar-link", source)

    def test_sidebar_intelligence_reuses_toolbar_filter(self) -> None:
        from pathlib import Path

        source = Path("static/js/rmc-sidebar-intelligence.js").read_text(encoding="utf-8")
        self.assertIn("bindToolbarFilterBar(root, ad, state)", source)
        self.assertIn("[data-rmc-sidebar-prefs-toggle]", source)
        self.assertIn("var usesToolbarFilter = bindToolbarFilterBar(root, ad, state)", source)

    def test_portal_base_loads_workspace_edge_fit(self) -> None:
        from django.template.loader import get_template

        source = get_template("portal_base.html").template.source
        self.assertIn("rmc-platform-workspace-edge-fit.css", source)


class NavSidebarRenderContractTests(SimpleTestCase):
    databases = {"default"}

    def setUp(self) -> None:
        self.factory = RequestFactory()

    def _manager_request(self):
        from apps.siteconfig.cockpit_context import cockpit_context
        from apps.siteconfig.models import SiteSettings

        request = self.factory.get("/super/", HTTP_HOST="manager.runmycampus.com")
        request.public_host_kind = "manager"
        site = SiteSettings(pk=1)
        site.cockpit_payload = {}
        request.SITE = site
        request.site_settings = site
        request.user = type(
            "AuthenticatedOperator",
            (),
            {"is_authenticated": True, "is_anonymous": False},
        )()
        ctx = cockpit_context(request)
        ctx["request"] = request
        ctx["csp_nonce"] = "test-nonce"
        return ctx

    def test_page_data_renders_when_nav_sidebar_enabled(self) -> None:
        ctx = self._manager_request()
        self.assertTrue((ctx.get("cockpit") or {}).get("nav_sidebar", {}).get("enabled"))
        tpl = Template("{% include 'partials/rmc_nav_sidebar_page_data.html' %}")
        rendered = tpl.render(Context(ctx))
        self.assertIn('id="page-data-rmc-nav-sidebar"', rendered)
        self.assertIn('"enabled": true', rendered)
        self.assertIn('"default_width": 280', rendered)


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    ROOT_URLCONF="config.manager_urls",
    SESSION_PINNING_ENABLED=False,
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
)
class NavSidebarManagerHttpTests(TestCase):
    _MANAGER_HOST = "manager.runmycampus.com"
    _PASSWORD = "testpass123"

    def setUp(self):
        import uuid

        self.user = User.objects.create_user(
            username=f"nav_sidebar_http_{uuid.uuid4().hex[:10]}",
            password=self._PASSWORD,
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client(HTTP_HOST=self._MANAGER_HOST)
        login_manager_control_plane(
            self.client,
            self.user,
            password=self._PASSWORD,
            host=self._MANAGER_HOST,
        )

    def _assert_nav_sidebar_in_body(self, body: str) -> None:
        self.assertIn('id="page-data-rmc-nav-sidebar"', body)
        self.assertIn("rmc-nav-sidebar.js", body)
        self.assertIn("rmc-nav-sidebar.css", body)
        self.assertIn("rmc-nav-sidebar__toggle", body)
        self.assertIn("rmc-nav-sidebar__resize-handle", body)

    def test_super_dashboard_ships_nav_sidebar(self) -> None:
        response = self.client.get("/super/")
        self.assertEqual(response.status_code, 200)
        self._assert_nav_sidebar_in_body(response.content.decode())

    def test_admin_index_ships_nav_sidebar(self) -> None:
        response = self.client.get("/admin/")
        self.assertEqual(response.status_code, 200)
        self._assert_nav_sidebar_in_body(response.content.decode())
