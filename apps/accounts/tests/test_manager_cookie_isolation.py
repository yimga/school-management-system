from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, TestCase, override_settings

from apps.accounts.middleware import ManagerCookieIsolationMiddleware
from apps.accounts.models import User
from apps.schools.models import School


@override_settings(ALLOWED_HOSTS=["*"])
class ManagerCookieIsolationMiddlewareTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    def test_manager_cookie_aliases_to_default_names_on_request(self):
        captured = {}

        def _response(request):
            captured["sessionid"] = request.COOKIES.get("sessionid")
            captured["csrftoken"] = request.COOKIES.get("csrftoken")
            return HttpResponse("ok")

        middleware = ManagerCookieIsolationMiddleware(_response)
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self.factory.get(
                "/authentication/login/",
                HTTP_HOST="manager.runmycampus.com",
                HTTP_COOKIE="rmc_manager_sessionid=session-123; rmc_manager_csrftoken=csrf-456",
            )
            middleware(request)

        self.assertEqual(captured["sessionid"], "session-123")
        self.assertEqual(captured["csrftoken"], "csrf-456")

    def test_manager_cookie_aliases_over_blank_default_cookie(self):
        captured = {}

        def _response(request):
            captured["sessionid"] = request.COOKIES.get("sessionid")
            captured["csrftoken"] = request.COOKIES.get("csrftoken")
            return HttpResponse("ok")

        middleware = ManagerCookieIsolationMiddleware(_response)
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self.factory.get(
                "/authentication/login/",
                HTTP_HOST="manager.runmycampus.com",
                HTTP_COOKIE='rmc_manager_sessionid=session-123; sessionid=""; rmc_manager_csrftoken=csrf-456; csrftoken=""',
            )
            middleware(request)

        self.assertEqual(captured["sessionid"], "session-123")
        self.assertEqual(captured["csrftoken"], "csrf-456")

    def test_manager_cookie_rewrites_response_cookie_names(self):
        def _response(_request):
            response = HttpResponse("ok")
            response.set_cookie(
                "sessionid", "session-123", httponly=True, samesite="Lax"
            )
            response.set_cookie("csrftoken", "csrf-456", samesite="Lax")
            return response

        middleware = ManagerCookieIsolationMiddleware(_response)
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self.factory.get(
                "/authentication/login/", HTTP_HOST="manager.runmycampus.com"
            )
            response = middleware(request)

        self.assertIn("rmc_manager_sessionid", response.cookies)
        self.assertIn("rmc_manager_csrftoken", response.cookies)
        self.assertEqual(response.cookies["rmc_manager_sessionid"].value, "session-123")
        self.assertEqual(response.cookies["rmc_manager_csrftoken"].value, "csrf-456")
        self.assertEqual(response.cookies["sessionid"]["max-age"], 0)
        self.assertEqual(response.cookies["csrftoken"]["max-age"], 0)

    def test_tenant_host_aliases_manager_cookies_when_sessionid_missing(self):
        """Cross-host “Open as school”: manager session cookie must map to sessionid on tenant."""
        captured = {}

        def _response(request):
            captured["sessionid"] = request.COOKIES.get("sessionid")
            captured["csrftoken"] = request.COOKIES.get("csrftoken")
            return HttpResponse("ok")

        middleware = ManagerCookieIsolationMiddleware(_response)
        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            request = self.factory.get(
                "/authentication/impersonate/",
                HTTP_HOST="tenant-alpha.runmycampus.com",
                HTTP_COOKIE="rmc_manager_sessionid=session-abc; rmc_manager_csrftoken=csrf-xyz",
            )
            middleware(request)

        self.assertEqual(captured["sessionid"], "session-abc")
        self.assertEqual(captured["csrftoken"], "csrf-xyz")


@override_settings(ALLOWED_HOSTS=["*"], JIT_IMPERSONATION_REQUIRE_CONSENT=False)
class EndImpersonationRedirectTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Tenant Alpha",
            slug="tenant-alpha",
            subdomain="tenant-alpha",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="support-manager",
            password="testpass123",
            is_superuser=True,
            is_staff=True,
        )

    def test_end_impersonation_redirects_back_to_manager_host(self):
        self.client.force_login(self.user)
        session = self.client.session
        session["impersonation"] = {
            "school_id": str(self.school.id),
            "actor_id": self.user.id,
        }
        session.save()

        with patch.dict(
            "os.environ", {"MULTI_TENANT_BASE_DOMAIN": "runmycampus.com"}, clear=False
        ):
            response = self.client.get(
                "/authentication/end-impersonation/",
                HTTP_HOST="tenant-alpha.runmycampus.com",
            )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "https://manager.runmycampus.com/super/")
