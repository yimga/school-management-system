"""Inline MFA wizard on profile posts through shared flow."""

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse


class MfaInlineProfileTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="inline_mfa_user",
            email="inline@mfa.test",
            password="Test1234!",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def test_profile_renders_inline_wizard_section(self):
        r = self.client.get(reverse("accounts:user_profile"))
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "profile-mfa-wizard")
        self.assertContains(r, "mfa_inline")

    def test_enable_mfa_inline_returns_qr_on_profile(self):
        r = self.client.post(
            reverse("accounts:user_profile"),
            {"mfa_inline": "1", "enable_mfa": "1"},
            follow=False,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "data:image/png;base64,")
