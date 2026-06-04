"""Fast shell contract checks (no DB): resolver + template fragments."""

from __future__ import annotations

from types import SimpleNamespace

from django.template.loader import render_to_string
from django.test import RequestFactory, SimpleTestCase, override_settings

from apps.platform_runtime.rmc_os_shell import resolve_rmc_os_shell


class ResolveRmcOsShellTests(SimpleTestCase):
    def test_anonymous_public_surface(self):
        rf = RequestFactory()
        req = rf.get("/portal/")
        req.user = SimpleNamespace(is_authenticated=False)
        req.public_host_kind = "tenant"
        req.session = {}
        out = resolve_rmc_os_shell(req)
        self.assertEqual(out["role_cluster"], "anonymous")
        self.assertEqual(out["surface_kind"], "public")

    def test_manager_superuser_founder_operator(self):
        rf = RequestFactory()
        req = rf.get("/super/")
        req.user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=True,
            role="ADMIN",
        )
        req.public_host_kind = "manager"
        req.session = {}
        out = resolve_rmc_os_shell(req)
        self.assertEqual(out["role_cluster"], "founder_operator")
        self.assertEqual(out["surface_kind"], "control-plane")

    def test_manager_non_super_operator(self):
        rf = RequestFactory()
        req = rf.get("/super/")
        req.user = SimpleNamespace(
            is_authenticated=True,
            is_superuser=False,
            role="ADMIN",
        )
        req.public_host_kind = "manager"
        req.session = {}
        out = resolve_rmc_os_shell(req)
        self.assertEqual(out["role_cluster"], "operator")


@override_settings(
    MIDDLEWARE=[
        "django.middleware.security.SecurityMiddleware",
        "django.contrib.sessions.middleware.SessionMiddleware",
        "django.middleware.common.CommonMiddleware",
        "django.middleware.csrf.CsrfViewMiddleware",
        "django.contrib.auth.middleware.AuthenticationMiddleware",
        "django.contrib.messages.middleware.MessageMiddleware",
    ],
)
class UnifiedShellTemplateFragmentTests(SimpleTestCase):
    """Marker contracts on partials (minimal context)."""

    def test_shell_portal_wrap_has_os_attributes(self):
        rf = RequestFactory()
        request = rf.get("/portal/foo/")
        request.user = SimpleNamespace(is_authenticated=False)
        request.public_host_kind = "tenant"
        request.session = {}
        request.school = None
        html = render_to_string(
            "partials/shell_portal_layout_wrap_open.html",
            {
                "request": request,
                "rmc_shell": SimpleNamespace(portal_wrap_authenticated_shell="tenant-portal"),
                "rmc_os_shell": {
                    "surface_kind": "tenant-portal",
                    "role_cluster": "anonymous",
                    "page_slug": "portal-foo",
                    "nav_job_clusters": ("school_command", "people"),
                },
            },
        )
        self.assertIn("data-rmc-os-shell=", html)
        self.assertIn('data-rmc-os-role="anonymous"', html)
        self.assertIn('data-rmc-os-page="portal-foo"', html)
        self.assertIn("data-rmc-os-nav-groups=", html)

    def test_rmc_os_page_header_renders(self):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = SimpleNamespace(is_authenticated=True, username="u")
        request.school = SimpleNamespace(name="Demo High")
        html = render_to_string(
            "components/rmc_os_page_header.html",
            {
                "request": request,
                "rmc_os_shell": {
                    "page_slug": "accounts-backend-dashboard",
                    "role_display": "Administrator",
                },
                "page_title": "Backend Dashboard",
            },
        )
        self.assertIn('data-rmc-os-page-header="1"', html)
        self.assertIn('data-rmc-os-page-purpose="1"', html)
        self.assertIn("Demo High", html)

    def test_rmc_os_status_strip_renders_safe_when_empty(self):
        rf = RequestFactory()
        request = rf.get("/")
        request.user = SimpleNamespace(is_authenticated=True)
        html = render_to_string(
            "components/rmc_os_status_strip.html",
            {
                "request": request,
                "platform_status_strip": None,
                "operator_incident_banner": None,
                "tenant_incident_banner": None,
                "rmc_offline_sync_state": {"pending": 0, "failed": 0, "conflicts": 0},
            },
        )
        self.assertIn('data-rmc-os-status-strip="1"', html)
        self.assertIn('data-rmc-payment-readiness-slot="1"', html)
        self.assertIn("data-rmc-offline-sync-bar", html)

    def test_rmc_os_context_rail_marker(self):
        html = render_to_string("components/rmc_os_context_rail.html", {})
        self.assertIn('data-rmc-context-rail="1"', html)
