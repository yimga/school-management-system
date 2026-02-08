from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


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
