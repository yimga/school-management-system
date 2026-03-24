from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


User = get_user_model()


class SiteConfigRedirectSafetyTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser(
            username="siteconfig-admin",
            email="siteconfig-admin@example.com",
            password="password",
        )
        self.client.force_login(self.user)

    def test_set_default_dashboard_view_rejects_external_next(self):
        response = self.client.post(
            reverse("siteconfig:set_default_dashboard_view"),
            {"view": "OVERVIEW", "next": "https://evil.example/phish"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("accounts:redirect"))

    def test_toggle_preview_mode_rejects_external_next(self):
        response = self.client.get(
            reverse("siteconfig:toggle_preview_mode"),
            {"next": "https://evil.example/phish"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/")

    def test_theme_experience_redirect_drops_external_next(self):
        response = self.client.get(
            reverse("siteconfig:theme_experience_redirect"),
            {"next": "https://evil.example/phish"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("studio_os:experience"))
