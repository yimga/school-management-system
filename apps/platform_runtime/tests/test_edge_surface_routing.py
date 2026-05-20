"""
Stage 3: edge host routing, urlconf switching, path guards, version endpoint.
"""

from __future__ import annotations

from unittest.mock import patch

from django.http import HttpResponse
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import resolve

from apps.schools.host_routing import public_host_kind
from apps.schools.middleware import ReservedPublicHostAccessMiddleware, UrlConfSwitcherMiddleware
from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class PublicHostKindMatrixTests(TestCase):
    def test_four_shell_host_kinds(self):
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            self.assertEqual(public_host_kind("runmycampus.com"), "base")
            self.assertEqual(public_host_kind("manager.runmycampus.com"), "manager")
            self.assertIsNone(public_host_kind("demo-school.runmycampus.com"))
            self.assertEqual(public_host_kind("localhost"), "local")


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class UrlConfSwitcherMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = UrlConfSwitcherMiddleware(lambda r: HttpResponse("ok"))

    def _process(self, host: str, path: str = "/"):
        request = self.factory.get(path, HTTP_HOST=host)
        self.middleware.process_request(request)
        return request

    def test_manager_host_uses_manager_urlconf(self):
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._process("manager.runmycampus.com")
        self.assertEqual(request.urlconf, "config.manager_urls")
        self.assertEqual(request.public_host_kind, "manager")

    def test_base_host_uses_public_urlconf(self):
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._process("runmycampus.com", "/marketing/")
        self.assertEqual(request.urlconf, "config.public_urls")
        self.assertEqual(request.public_host_kind, "base")

    def test_tenant_subdomain_uses_tenant_urlconf(self):
        School.objects.create(
            name="Edge Demo",
            slug="edge-demo",
            subdomain="edge-demo",
            is_active=True,
        )
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self._process("edge-demo.runmycampus.com")
        self.assertEqual(request.urlconf, "config.tenant_urls")
        self.assertIsNone(request.public_host_kind)


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class ReservedPublicHostPathGuardTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = ReservedPublicHostAccessMiddleware(
            lambda r: HttpResponse("ok")
        )

    def test_super_on_tenant_host_redirects_to_manager(self):
        School.objects.create(
            name="Edge Beta",
            slug="edge-beta",
            subdomain="edge-beta",
            is_active=True,
        )
        request = self.factory.get(
            "/super/dashboard/", HTTP_HOST="edge-beta.runmycampus.com"
        )
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            response = self.middleware.process_request(request)
        self.assertIsNotNone(response)
        self.assertIn(response.status_code, (301, 302, 303, 307, 308))
        self.assertIn("manager.runmycampus.com", response["Location"])

    def test_super_on_base_host_redirects_to_manager(self):
        request = self.factory.get("/super/", HTTP_HOST="runmycampus.com")
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            response = self.middleware.process_request(request)
        self.assertIsNotNone(response)
        self.assertIn("manager.runmycampus.com", response["Location"])

    def test_manager_host_allows_configuration_prefix(self):
        request = self.factory.get("/configuration/", HTTP_HOST="manager.runmycampus.com")
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            response = self.middleware.process_request(request)
        self.assertIsNone(response)


@override_settings(
    ALLOWED_HOSTS=["*", "manager.runmycampus.com", "runmycampus.com"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class EdgeSurfaceHttpRoutingTests(TestCase):
    def test_version_endpoint_on_default_urlconf(self):
        response = Client().get("/-/version/")
        self.assertEqual(response.status_code, 200)
        self.assertIn("commit_sha", response.json())

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_version_on_manager_host(self):
        response = Client(HTTP_HOST="manager.runmycampus.com").get("/-/version/")
        self.assertEqual(response.status_code, 200)

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_configuration_resolves_on_manager(self):
        match = resolve("/configuration/", urlconf="config.manager_urls")
        self.assertEqual(match.namespace, "configuration")

    @override_settings(ROOT_URLCONF="config.manager_urls")
    def test_internal_admin_alias_on_manager(self):
        match = resolve("/internal-admin/", urlconf="config.manager_urls")
        self.assertEqual(match.url_name, "internal_admin")


@override_settings(ALLOWED_HOSTS=["*"], MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class HostHeaderHardeningTests(TestCase):
    def test_public_path_on_unknown_host_redirects_to_canonical_base(self):
        """PublicPathRedirectMiddleware must not serve marketing on arbitrary tenant hosts."""
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            response = Client(HTTP_HOST="evil.attacker.example").get("/marketing/")
        self.assertIn(response.status_code, (301, 302, 303, 307, 308))
        location = response["Location"]
        self.assertIn("runmycampus.com", location)
        self.assertNotIn("evil.attacker", location)

    def test_validate_host_rejects_arbitrary_host_when_allowlist_tight(self):
        from django.conf import settings
        from django.http.request import validate_host

        with self.settings(
            ALLOWED_HOSTS=["runmycampus.com", "manager.runmycampus.com", "testserver"]
        ):
            self.assertFalse(
                validate_host("evil.attacker.example", settings.ALLOWED_HOSTS)
            )


@override_settings(ALLOWED_HOSTS=["*"])
class FourShellTemplateContractTests(TestCase):
    """Static contract: four shells load cascade partials before paint."""

    def test_marketing_shell_includes_theme_cascade(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        text = (root / "templates/marketing/base_marketing.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("partials/rmc_theme_meta.html", text)
        self.assertIn("js/theme-preference-bootstrap.js", text)
        self.assertIn('data-surface="marketing"', text)

    def test_control_plane_shell_includes_theme_cascade(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        text = (root / "templates/control_plane_skeleton.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("partials/rmc_theme_meta.html", text)
        self.assertIn('data-surface="control-plane"', text)

    def test_portal_shell_includes_theme_cascade(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        text = (root / "templates/portal_base.html").read_text(encoding="utf-8")
        self.assertIn("partials/rmc_theme_meta.html", text)
        self.assertIn("js/theme-preference-bootstrap.js", text)

    def test_admin_shell_includes_theme_cascade(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[3]
        text = (root / "templates/admin/base_site.html").read_text(encoding="utf-8")
        self.assertIn("partials/rmc_theme_meta.html", text)
        self.assertIn("js/theme-preference-bootstrap.js", text)
