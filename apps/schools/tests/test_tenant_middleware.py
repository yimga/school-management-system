import os
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.middleware import (
    LegacyBaseDomainRedirectMiddleware,
    ReservedPublicHostAccessMiddleware,
    TenantMiddleware,
    UrlConfSwitcherMiddleware,
)
from apps.schools.models import School, SchoolDomain


@override_settings(ALLOWED_HOSTS=["*"])
class TenantMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Tenant Alpha",
            slug="tenant-alpha",
            subdomain="tenant-alpha",
            is_active=True,
        )
        self.middleware = TenantMiddleware(lambda request: None)

    def _request(self, path: str, host: str):
        request = self.factory.get(path, HTTP_HOST=host)
        SessionMiddleware(lambda r: None).process_request(request)
        request.session.save()
        request.user = AnonymousUser()
        return request

    def test_sets_school_and_session_for_subdomain_host(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False):
            request = self._request("/portal/", "tenant-alpha.example.com")
            response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertEqual(request.school.id, self.school.id)
        self.assertEqual(request.session.get("school_id"), str(self.school.id))

    def test_clears_stale_session_school_when_no_tenant_resolved(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False):
            request = self._request("/public/", "example.com")
            request.session["school_id"] = str(self.school.id)
            request.session.save()
            response = self.middleware.process_request(request)

        self.assertIsNone(response)
        self.assertIsNone(request.school)
        self.assertNotIn("school_id", request.session)

    def test_rewrites_tenant_path_prefix_and_preserves_school_scope(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "example.com"}, clear=False):
            request = self._request("/t/tenant-alpha/authentication/login/", "example.com")
            response = self.middleware.process_request(request)

        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://tenant-alpha.example.com/authentication/login/")

    def test_resolves_verified_schooldomain_custom_host(self):
        SchoolDomain.objects.create(
            school=self.school,
            domain="portal.tenant-alpha.edu",
            kind=SchoolDomain.Kind.CUSTOM,
            is_verified=True,
        )
        request = self._request("/portal/", "portal.tenant-alpha.edu")
        response = self.middleware.process_request(request)
        self.assertIsNone(response)
        self.assertEqual(request.school.id, self.school.id)

    @override_settings(DEBUG=False)
    def test_unknown_tenant_host_redirects_to_root_school_not_found(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/portal/", "unknown.runmycampus.com")
            response = self.middleware.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://runmycampus.com/school-not-found/?slug=unknown")

    @override_settings(DEBUG=False)
    def test_tenant_path_fallback_redirects_to_subdomain_in_production(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/t/tenant-alpha/authentication/login/", "runmycampus.com")
            response = self.middleware.process_request(request)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://tenant-alpha.runmycampus.com/authentication/login/")


@override_settings(ALLOWED_HOSTS=["*"])
class UrlConfSwitcherMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.middleware = UrlConfSwitcherMiddleware(lambda request: None)

    def _request(self, path: str, host: str):
        request = self.factory.get(path, HTTP_HOST=host)
        request.user = AnonymousUser()
        return request

    def test_base_domain_uses_public_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/", "runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_www_base_domain_uses_public_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/", "www.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_subdomain_uses_tenant_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/", "lycee-douala.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.tenant_urls")

    def test_tenant_path_prefix_on_base_domain_uses_public_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/t/lycee-douala/authentication/login/", "runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_reserved_verify_host_uses_public_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/", "verify.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_reserved_support_host_uses_public_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/", "support.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_manager_host_uses_manager_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/", "manager.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.manager_urls")

    def test_api_host_uses_api_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/", "api.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.api_urls")

    def test_docs_host_uses_docs_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/", "docs.runmycampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.docs_urls")


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False)
class LegacyAndReservedHostMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.legacy = LegacyBaseDomainRedirectMiddleware(lambda request: None)
        self.reserved = ReservedPublicHostAccessMiddleware(lambda request: None)

    def _request(self, path: str, host: str):
        request = self.factory.get(path, HTTP_HOST=host)
        request.user = AnonymousUser()
        return request

    def test_legacy_domain_redirects_to_canonical(self):
        with patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "oldcampus.com",
            },
            clear=False,
        ):
            request = self._request("/find/?q=gilead", "oldcampus.com")
            response = self.legacy.process_request(request)
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response["Location"], "https://runmycampus.com/find/?q=gilead")

    def test_verify_host_redirects_root_to_verify_hub(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/", "verify.runmycampus.com")
            response = self.reserved.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/verify/")

    def test_base_authentication_path_redirects_to_manager_for_browser(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/authentication/login/", "runmycampus.com")
            request.META["HTTP_USER_AGENT"] = "Mozilla/5.0"
            response = self.reserved.process_request(request)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://manager.runmycampus.com/authentication/login/")

    def test_render_probe_to_auth_login_is_not_redirected(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False):
            request = self._request("/authentication/login/", "school-management-system-2kzk.onrender.com")
            request.META["HTTP_USER_AGENT"] = "Render/1.0"
            response = self.reserved.process_request(request)
        self.assertIsNotNone(response)
        self.assertEqual(response.status_code, 200)
