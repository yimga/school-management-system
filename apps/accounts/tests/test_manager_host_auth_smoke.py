"""Manager host (control plane): critical auth URLs still resolve and respond (batch 7 #69 / batch 16)."""

from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(ALLOWED_HOSTS=["*", "manager.runmycampus.com", "testserver"])
class ManagerHostAuthSmokeTests(TestCase):
    """Smoke for manager urlconf + accounts namespace when hosts or paths shift."""

    host = "manager.runmycampus.com"

    def test_login_returns_200_on_manager_host(self):
        url = reverse("accounts:login")
        r = self.client.get(url, HTTP_HOST=self.host)
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"data-rmc-password-toggle", r.content)
        self.assertIn(b"rmc-password-toggle.js", r.content)

    def test_password_change_requires_login_on_manager_host(self):
        url = reverse("accounts:password_change")
        r = self.client.get(url, HTTP_HOST=self.host)
        self.assertIn(r.status_code, (302, 301))
        self.assertIn("login", (r.url or "").lower())

    def test_sessions_page_requires_login_on_manager_host(self):
        url = reverse("accounts:sessions_page")
        r = self.client.get(url, HTTP_HOST=self.host)
        self.assertIn(r.status_code, (302, 301))
