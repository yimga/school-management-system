import os
from unittest.mock import patch

from django.contrib.auth.models import AnonymousUser
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.middleware import TenantMiddleware, UrlConfSwitcherMiddleware
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

        self.assertIsNone(response)
        self.assertEqual(request.school.id, self.school.id)
        self.assertEqual(request.tenant_path_prefix, "/t/tenant-alpha/")
        self.assertEqual(request.path, "/authentication/login/")
        self.assertEqual(request.path_info, "/authentication/login/")
        self.assertEqual(request.META.get("PATH_INFO"), "/authentication/login/")
        self.assertEqual(request.session.get("school_id"), str(self.school.id))

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
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runyourcampus.com"}, clear=False):
            request = self._request("/", "runyourcampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_www_base_domain_uses_public_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runyourcampus.com"}, clear=False):
            request = self._request("/", "www.runyourcampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.public_urls")

    def test_subdomain_uses_tenant_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runyourcampus.com"}, clear=False):
            request = self._request("/", "lycee-douala.runyourcampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.tenant_urls")

    def test_tenant_path_prefix_uses_tenant_urlconf(self):
        with patch.dict(os.environ, {"MULTI_TENANT_BASE_DOMAIN": "runyourcampus.com"}, clear=False):
            request = self._request("/t/lycee-douala/authentication/login/", "runyourcampus.com")
            self.middleware.process_request(request)
        self.assertEqual(request.urlconf, "config.tenant_urls")
