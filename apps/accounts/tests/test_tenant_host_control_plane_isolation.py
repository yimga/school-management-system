from unittest.mock import patch
from urllib.parse import urlparse

from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.middleware import TenantHostControlPlaneIsolationMiddleware
from apps.accounts.models import User
from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"])
class TenantHostControlPlaneIsolationMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Tenant Alpha",
            slug="tenant-alpha",
            subdomain="tenant-alpha",
            is_active=True,
        )
        self.superadmin = User.objects.create_user(
            username="tenant_host_superadmin",
            password="testpass123",
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=False,
        )

    def _request(self, path="/portal/teacher/"):
        request = self.factory.get(path, HTTP_HOST="tenant-alpha.runmycampus.com")
        SessionMiddleware(lambda req: HttpResponse("ok")).process_request(request)
        request.session.save()
        request.user = self.superadmin
        request.school = self.school
        # Production reality: a tenant subdomain resolves to public_host_kind=None
        # (never the literal "tenant"); the guard keys off the positive is_tenant_host
        # marker set by UrlConfSwitcherMiddleware.
        request.public_host_kind = None
        request.is_tenant_host = True
        return request

    def test_superadmin_without_impersonation_is_redirected_to_manager_host(self):
        middleware = TenantHostControlPlaneIsolationMiddleware(
            lambda request: HttpResponse("ok")
        )
        request = self._request()

        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            response = middleware(request)

        self.assertEqual(response.status_code, 302)
        loc = urlparse(response["Location"])
        self.assertEqual(loc.netloc, "manager.runmycampus.com")
        self.assertTrue(
            (loc.path or "").rstrip("/").endswith("/super"),
            msg=response["Location"],
        )
        self.assertIn(loc.scheme, ("http", "https"))

    def test_superadmin_with_matching_impersonation_session_is_allowed(self):
        middleware = TenantHostControlPlaneIsolationMiddleware(
            lambda request: HttpResponse("ok")
        )
        request = self._request()
        request.session["impersonation"] = {
            "school_id": str(self.school.id),
            "actor_id": self.superadmin.id,
        }
        request.session.save()

        response = middleware(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
