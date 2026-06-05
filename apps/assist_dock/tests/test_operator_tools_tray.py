"""v4.02.0 — Operator Tools edge-tray registry + shell wiring tests."""

from __future__ import annotations

from django.template import Context, Template
from django.test import Client, RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.assist_dock.registry import SURFACE_MANAGER, get_slots_for
from apps.schools.tests.manager_client import login_manager_control_plane


class OperatorToolsSlotsTests(SimpleTestCase):
    """Registry includes tray-native utilities on manager surface."""

    EXPECTED_IDS = frozenset(
        {
            "operator-notebook",
            "keyboard-shortcuts",
            "copy-page-link",
            "on-this-page",
            "command-search",
            "platform-status",
            "open-incidents",
            "security-posture",
            "live-activity",
            "live-cursors",
        }
    )

    def test_manager_surface_includes_operator_tools_slots(self) -> None:
        ids = {slot.id for slot in get_slots_for(surface=SURFACE_MANAGER, role="SUPERADMIN")}
        missing = self.EXPECTED_IDS - ids
        self.assertFalse(missing, f"missing operator tools slots: {sorted(missing)}")

    def test_platform_health_unpinned_by_default(self) -> None:
        slots = {s.id: s for s in get_slots_for(surface=SURFACE_MANAGER, role="SUPERADMIN")}
        health = slots.get("platform-health")
        self.assertIsNotNone(health)
        self.assertFalse(health.pinned_default)

    def test_workflow_progress_unpinned_by_default(self) -> None:
        slots = {s.id: s for s in get_slots_for(surface=SURFACE_MANAGER, role="SUPERADMIN")}
        wf = slots.get("workflow-progress")
        self.assertIsNotNone(wf)
        self.assertFalse(wf.pinned_default)


class OperatorToolsCockpitDefaultsTests(SimpleTestCase):
    def test_manager_200x_includes_operator_tools_defaults(self) -> None:
        from apps.siteconfig.cockpit_manager_200x import manager_200x_defaults

        payload = manager_200x_defaults()
        tools = payload.get("operator_tools")
        self.assertIsInstance(tools, dict)
        self.assertTrue(tools.get("enabled"))
        self.assertEqual(tools.get("layout"), "edge-tray")
        self.assertTrue(tools.get("hide_floating_notebook"))


class OperatorToolsShellTemplateTests(SimpleTestCase):
    def test_control_plane_skeleton_wires_tray_assets(self) -> None:
        from django.template.loader import get_template

        source = get_template("control_plane_skeleton.html").template.source
        self.assertIn("rmc_operator_tools_styles.html", source)
        self.assertIn("rmc_operator_tools_scripts.html", source)
        self.assertNotIn('data-rmc-back-to-top-policy="always"', source)

    def test_admin_base_site_wires_tray_on_manager_host(self) -> None:
        from django.template.loader import get_template

        source = get_template("admin/base_site.html").template.source
        self.assertIn("rmc_operator_tools_styles.html", source)
        self.assertIn("rmc_operator_tools_scripts.html", source)
        self.assertIn("is_manager_host", source)

    def test_portal_base_wires_tenant_tools_not_operator_inline(self) -> None:
        from django.template.loader import get_template

        source = get_template("portal_base.html").template.source
        self.assertIn("rmc_tenant_tools_styles.html", source)
        self.assertIn("rmc_tenant_tools_scripts.html", source)
        self.assertIn("rmc_operator_tools_scripts.html", source)
        self.assertNotIn('id="page-data-rmc-operator-tools"', source)
        self.assertNotIn('id="page-data-rmc-tenant-tools"', source)
        self.assertIn("cockpit.tenant_tools.enabled", source)


class OperatorToolsRenderContractTests(SimpleTestCase):
    """Render operator-tools partials with live cockpit_context (no view assumptions)."""

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
        ctx["platform_incidents_url"] = "/super/command-center/"
        return ctx

    def test_page_data_renders_when_operator_tools_enabled(self) -> None:
        ctx = self._manager_request()
        self.assertTrue((ctx.get("cockpit") or {}).get("operator_tools", {}).get("enabled"))
        tpl = Template(
            "{% load static marketing_public_urls %}"
            "{% include 'partials/rmc_operator_tools_page_data.html' %}"
        )
        rendered = tpl.render(Context(ctx))
        self.assertIn('id="page-data-rmc-operator-tools"', rendered)
        self.assertIn('"enabled": true', rendered)
        self.assertIn('"layout":', rendered)
        self.assertIn("tray", rendered)

    def test_scripts_partial_renders_tray_js_on_manager_host(self) -> None:
        ctx = self._manager_request()
        tpl = Template("{% load static %}{% include 'partials/rmc_operator_tools_scripts.html' %}")
        rendered = tpl.render(Context(ctx))
        self.assertIn("rmc-operator-tools-tray.js", rendered)

    def test_styles_partial_renders_tray_css_on_manager_host(self) -> None:
        ctx = self._manager_request()
        tpl = Template("{% load static %}{% include 'partials/rmc_operator_tools_styles.html' %}")
        rendered = tpl.render(Context(ctx))
        self.assertIn("rmc-operator-tools-tray.css", rendered)


@override_settings(
    ALLOWED_HOSTS=["*", "testserver", "127.0.0.1", "localhost", "manager.runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
    ROOT_URLCONF="config.manager_urls",
    SESSION_PINNING_ENABLED=False,
    OPERATOR_MFA_REQUIRED_ON_MANAGER=False,
)
class OperatorToolsManagerHttpTests(TestCase):
    """Live HTML contract on manager /super/ and /admin/ (not assumed from templates alone)."""

    _MANAGER_HOST = "manager.runmycampus.com"
    _PASSWORD = "testpass123"

    def setUp(self):
        import uuid

        self.user = User.objects.create_user(
            username=f"operator_tools_http_{uuid.uuid4().hex[:10]}",
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

    def _assert_operator_tools_in_body(self, body: str) -> None:
        self.assertIn('id="page-data-rmc-operator-tools"', body)
        self.assertIn("rmc-operator-tools-tray.js", body)
        self.assertIn("rmc-operator-tools-tray.css", body)
        self.assertNotIn('data-rmc-back-to-top-policy="always"', body)

    def test_super_dashboard_ships_operator_tools_island(self) -> None:
        url = reverse("super:dashboard")
        response = self.client.get(url, HTTP_HOST=self._MANAGER_HOST)
        self.assertEqual(response.status_code, 200, msg=response.get("Location", ""))
        self._assert_operator_tools_in_body(response.content.decode("utf-8"))

    def test_manager_admin_ships_operator_tools_island(self) -> None:
        response = self.client.get("/admin/", HTTP_HOST=self._MANAGER_HOST)
        self.assertEqual(response.status_code, 200, msg=response.get("Location", ""))
        self._assert_operator_tools_in_body(response.content.decode("utf-8"))
