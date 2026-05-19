"""Platform operators on tenant host are redirected to manager siteconfig shell."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase, override_settings
from django.urls import reverse

from apps.siteconfig.middleware import OperatorSiteconfigManagerShellMiddleware
from apps.siteconfig.models import Plan
from apps.schools.models import School

_TENANT = "aicenter.runmycampus.com"
_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _TENANT, _MGR],
    ROOT_URLCONF="config.tenant_urls",
)
class OperatorSiteconfigManagerRedirectTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.plan = Plan.objects.create(name="Free", slug="basic", is_active=True)
        cls.school = School.objects.create(
            name="AI Center School",
            slug="aicenter",
            subdomain="aicenter",
            is_active=True,
            plan=cls.plan,
        )

    def test_middleware_redirects_superuser_ai_center_to_manager(self):
        User = get_user_model()
        User.objects.create_user(
            username="op_redirect",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST=_TENANT)
        client.login(username="op_redirect", password="x" * 8)
        path = reverse("siteconfig:ai_center", urlconf="config.tenant_urls")
        resp = client.get(path)
        self.assertEqual(resp.status_code, 302)
        loc = resp["Location"]
        self.assertIn("manager", loc)
        self.assertIn("/siteconfig/ai-center/", loc)

    def test_middleware_unit_redirects_operator_on_tenant_host(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="op_redirect_unit",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        rf = RequestFactory()
        request = rf.get("/siteconfig/ai-center/", HTTP_HOST=_TENANT)
        request.user = user

        def get_response(req):
            from django.http import HttpResponse

            return HttpResponse("ok")

        mw = OperatorSiteconfigManagerShellMiddleware(get_response)
        resp = mw(request)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("manager", resp["Location"])
        self.assertIn("/siteconfig/ai-center/", resp["Location"])

    def test_middleware_does_not_redirect_tenant_school_onboarding(self):
        """School activation checklist stays on tenant host (request.school context)."""
        User = get_user_model()
        user = User.objects.create_user(
            username="op_onboarding_tenant",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        rf = RequestFactory()
        request = rf.get("/siteconfig/onboarding/", HTTP_HOST=_TENANT)
        request.user = user

        def get_response(req):
            from django.http import HttpResponse

            return HttpResponse("ok")

        mw = OperatorSiteconfigManagerShellMiddleware(get_response)
        resp = mw(request)
        self.assertEqual(resp.status_code, 200)

    def test_middleware_passes_through_on_manager_host(self):
        User = get_user_model()
        user = User.objects.create_user(
            username="op_pass_mgr",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        rf = RequestFactory()
        request = rf.get("/siteconfig/ai-center/", HTTP_HOST=_MGR)
        request.public_host_kind = "manager"
        request.user = user

        def get_response(req):
            from django.http import HttpResponse

            return HttpResponse("ok")

        mw = OperatorSiteconfigManagerShellMiddleware(get_response)
        resp = mw(request)
        self.assertEqual(resp.status_code, 200)
