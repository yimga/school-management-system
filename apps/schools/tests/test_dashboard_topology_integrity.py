"""
Dual-dashboard topology integrity — boundary denial, route crawl, viewport markers.

Maps the sovereign dual-dashboard mandate to Django surfaces:
  platform_super (/super/) vs platform_config (/configuration/, /admin/)
  tenant_super (backend/portal) vs tenant_config (/admin/, siteconfig mutations)
"""

from __future__ import annotations

from pathlib import Path

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings

from apps.accounts.models import User
from apps.schools.dashboard_rbac import (
    classify_dashboard_tier,
    evaluate_dashboard_topology_access,
)
from apps.schools.middleware_dashboard_topology import DashboardTopologyRBACMiddleware
from apps.schools.super_admin_paired_surfaces import build_surface_parity_matrix

ROOT = Path(__file__).resolve().parents[3]


class DashboardTopologyClassificationTests(SimpleTestCase):
    def test_platform_super_vs_config_paths(self):
        class Req:
            path = "/super/"
            public_host_kind = "manager"

        self.assertEqual(classify_dashboard_tier(Req()), "platform_super")
        Req.path = "/configuration/domains/"
        self.assertEqual(classify_dashboard_tier(Req()), "platform_config")
        Req.path = "/admin/"
        self.assertEqual(classify_dashboard_tier(Req()), "platform_config")

    def test_tenant_super_vs_config_paths(self):
        class Req:
            path = "/authentication/backend/"
            public_host_kind = "tenant"
            school = object()

        self.assertEqual(classify_dashboard_tier(Req()), "tenant_super")
        Req.path = "/admin/"
        self.assertEqual(classify_dashboard_tier(Req()), "tenant_config")


class DashboardTopologyBoundaryViolationTests(TestCase):
    """Test 1: operational role cannot access tenant-config tier."""

    def setUp(self):
        self.factory = RequestFactory()
        self.teacher = User.objects.create_user(
            username="teacher_topo",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        self.admin = User.objects.create_user(
            username="admin_topo",
            password="testpass123",
            role=User.Role.ADMIN,
        )

    def _request(self, path: str, method: str = "GET", user=None):
        req = getattr(self.factory, method.lower())(path, HTTP_HOST="school.runmycampus.com")
        req.user = user or self.teacher
        req.public_host_kind = "tenant"
        req.headers = {"Accept": "text/html"}
        return req

    def test_teacher_denied_tenant_admin(self):
        decision = evaluate_dashboard_topology_access(self._request("/admin/"))
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.tier, "tenant_config")

    def test_teacher_denied_siteconfig_grading_post(self):
        decision = evaluate_dashboard_topology_access(
            self._request("/siteconfig/grading/", method="POST")
        )
        self.assertFalse(decision.allowed)

    def test_teacher_allowed_configure_hub_read(self):
        decision = evaluate_dashboard_topology_access(
            self._request("/portal/configure/", method="GET")
        )
        self.assertTrue(decision.allowed)

    def test_admin_allowed_siteconfig_grading(self):
        decision = evaluate_dashboard_topology_access(
            self._request("/siteconfig/grading/", user=self.admin)
        )
        self.assertTrue(decision.allowed)

    def test_middleware_returns_403_html(self):
        middleware = DashboardTopologyRBACMiddleware(lambda r: None)
        response = middleware.process_request(self._request("/admin/"))
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 403)
        self.assertIn(b"Configuration area restricted", response.content)


# The parity matrix probes the MANAGER-host operator spine: super:*, configuration:*,
# and the admin:* changelists. On the manager host those admin routes are served by
# platform_admin_site (config.manager_urls) — config.urls host-DISPATCHES /admin/, so
# admin:* names don't reverse there and the probe falsely reads "unreachable". Resolve
# the matrix against the urlconf it is actually served under (the manager host).
@override_settings(ROOT_URLCONF="config.manager_urls")
class DashboardTopologyMechanicalCrawlTests(SimpleTestCase):
    """Test 2: operator surface spine + paired routes resolve (no dead nav)."""

    def test_surface_parity_matrix_green(self):
        matrix = build_surface_parity_matrix()
        self.assertTrue(matrix["spine_ok"], matrix.get("spine"))
        self.assertTrue(matrix["pairs_ok"], matrix.get("super_first_pairs"))
        self.assertTrue(matrix["browser_probes_ok"], matrix.get("browser_probes"))


class DashboardTopologyViewportMarkerTests(SimpleTestCase):
    """Test 3: essential chrome stays viewport-safe across shells."""

    def test_user_dropdown_viewport_safe_and_logout(self):
        text = (ROOT / "templates" / "components" / "user_dropdown.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("data-rmc-shell-viewport-safe", text)
        self.assertIn("accounts:logout", text)
        # v4.01.43: the theme control moved from an inline `rmc-theme-btn` element
        # into the shared header_theme_chip component (rendered in the dropdown) +
        # rmc-theme-toggle.js. Assert the theme control is present via its component.
        self.assertIn("header_theme_chip.html", text)

    def test_control_plane_shell_uses_scrollable_main(self):
        skeleton = (ROOT / "templates" / "control_plane_skeleton.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("dashboard-topology-shell.css", skeleton)
        self.assertTrue(
            "overflow-y-auto" in skeleton
            or "data-rmc-shell-main" in skeleton
            or "min-h-0" in skeleton,
            "control plane shell must define scrollable main region",
        )

    def test_portal_shell_loads_topology_assets(self):
        portal = (ROOT / "templates" / "portal_base.html").read_text(encoding="utf-8")
        # v4.02.45 consolidated ~70 standalone portal CSS files into a deferred
        # bundle + the canonical spine; the retired dashboard-topology-shell.css
        # rules moved into design-tokens.css (data-rmc-shell-main) and
        # rmc-class-grammar.css (.rmc-dashboard-widget-boundary), both loaded
        # blocking here. Assert the widget-boundary JS + the grammar that styles it.
        self.assertIn("rmc-dashboard-widget-boundary.js", portal)
        self.assertIn("rmc-class-grammar.css", portal)


class DashboardTopologyContextProcessorTests(TestCase):
    def test_context_processor_registered(self):
        from django.conf import settings

        processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
        self.assertIn(
            "apps.schools.context_processors.dashboard_topology_context",
            processors,
        )


class DashboardTopologyRegistryTests(SimpleTestCase):
    def test_audit_matrix_green(self):
        from apps.schools.dashboard_topology_registry import (
            build_dashboard_topology_audit_matrix,
        )

        matrix = build_dashboard_topology_audit_matrix()
        self.assertTrue(matrix["ok"], matrix)


class DashboardTopologyMiddlewareWiringTests(TestCase):
    def test_middleware_registered(self):
        from django.conf import settings

        self.assertIn(
            "apps.schools.middleware_dashboard_topology.DashboardTopologyRBACMiddleware",
            settings.MIDDLEWARE,
        )

    def test_anonymous_passes_through(self):
        middleware = DashboardTopologyRBACMiddleware(lambda r: None)
        request = RequestFactory().get("/admin/", HTTP_HOST="school.runmycampus.com")
        request.user = AnonymousUser()
        request.public_host_kind = "tenant"
        self.assertIsNone(middleware.process_request(request))
