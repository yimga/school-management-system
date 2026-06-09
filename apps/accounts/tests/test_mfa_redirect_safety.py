from django.contrib.auth import get_user_model
from django.http import HttpResponse
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.middleware import RequireMFAMiddleware


User = get_user_model()


def _ok_response(request):
    return HttpResponse("ok")


class MfaRedirectSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="mfa-user",
            email="mfa-user@example.com",
            password="password",
        )
        self.client.force_login(self.user)

    def test_dismiss_mfa_banner_rejects_external_next(self):
        response = self.client.get(
            reverse("accounts:dismiss_mfa_banner"),
            {"next": "https://evil.example/phish"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/")


class RequireMfaPostLoginRedirectBypassTests(TestCase):
    """ADMIN owners must reach redirect_view before MFA setup (signup/onboarding path)."""

    def test_redirect_bypasses_mfa_gate_when_path_is_normalized(self):
        user = User.objects.create_user(
            username="new-owner",
            email="new-owner@example.com",
            password="password",
            role="ADMIN",
        )
        factory = RequestFactory()
        request = factory.get("/authentication/redirect/")
        request.user = user
        request.session = {}
        middleware = RequireMFAMiddleware(_ok_response)
        response = middleware(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.content, b"ok")
