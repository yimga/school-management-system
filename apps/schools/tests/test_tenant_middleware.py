import os
from unittest.mock import patch

from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.middleware import TenantMiddleware
from apps.schools.models import School


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
