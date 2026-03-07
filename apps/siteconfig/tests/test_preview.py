"""
Tests for site settings preview (preview_from_form view).
Ensures redirect URL includes preview_section and preview_keep when provided.
"""

from django.test import TestCase, Client
from django.contrib.auth import get_user_model
from django.urls import reverse
from apps.siteconfig.models import ThemePack
from apps.siteconfig.views import SESSION_KEY

User = get_user_model()


class PreviewFromFormTestCase(TestCase):
    """Test preview_from_form redirect URL and query params."""

    def setUp(self):
        self.client = Client()
        self.user = User.objects.create_superuser(
            username="previewtest",
            email="preview@test.com",
            password="password",
        )
        self.url = reverse("siteconfig:preview_from_form")

    def _post(self, data=None, **extra):
        data = dict(data or {}, csrfmiddlewaretoken="test")
        return self.client.post(self.url, data, **extra)

    def test_post_required_unauthenticated(self):
        """GET without auth must not return 200 (usually 302 redirect to login)."""
        response = self.client.get(self.url)
        self.assertIn(response.status_code, (302, 400, 405), "GET must not be accepted")
        self.assertNotEqual(response.status_code, 200)

    def test_get_when_logged_in_returns_bad_request(self):
        """GET when authenticated must return 400 (POST required)."""
        self.client.login(username="previewtest", password="password")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 400, "GET must return 400 when POST is required")

    def test_redirect_url_contains_preview_section_footer(self):
        self.client.login(username="previewtest", password="password")
        response = self._post({"preview_section": "footer"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("redirect_url", data)
        self.assertIn("preview_section=footer", data["redirect_url"])

    def test_redirect_url_contains_preview_section_header(self):
        self.client.login(username="previewtest", password="password")
        response = self._post({"preview_section": "header"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("preview_section=header", data["redirect_url"])

    def test_redirect_url_contains_preview_section_theme(self):
        self.client.login(username="previewtest", password="password")
        response = self._post({"preview_section": "theme-experience"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("preview_section=theme", data["redirect_url"])

    def test_redirect_url_login_section_goes_to_login_page(self):
        self.client.login(username="previewtest", password="password")
        response = self._post({"preview_section": "login"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("login", data["redirect_url"])
        self.assertIn("preview_section=login", data["redirect_url"])

    def test_redirect_url_preview_keep(self):
        self.client.login(username="previewtest", password="password")
        response = self._post({"preview_section": "footer", "preview_keep": "1"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("preview_section=footer", data["redirect_url"])
        self.assertIn("preview_keep=1", data["redirect_url"])

    def test_redirect_url_multiple_sections(self):
        self.client.login(username="previewtest", password="password")
        response = self._post({"preview_section": "footer,header"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("preview_section=", data["redirect_url"])
        self.assertIn("footer", data["redirect_url"])
        self.assertIn("header", data["redirect_url"])

    def test_redirect_url_contains_preview_section_sidebar(self):
        self.client.login(username="previewtest", password="password")
        response = self._post({"preview_section": "sidebar"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("preview_section=sidebar", data["redirect_url"])

    def test_theme_pack_and_checkbox_false_values_are_stored_in_preview_session(self):
        self.client.login(username="previewtest", password="password")
        site_pack = ThemePack.objects.create(
            name="Site Preview Pack",
            slug="site-preview-pack",
            primary_color="#0d6efd",
            accent_color="#198754",
            is_active=True,
            applies_to_admin=False,
        )
        admin_pack = ThemePack.objects.create(
            name="Admin Preview Pack",
            slug="admin-preview-pack",
            primary_color="#111827",
            accent_color="#38bdf8",
            is_active=True,
            applies_to_admin=True,
        )

        response = self._post(
            {
                "preview_section": "theme-experience",
                "theme_pack": str(site_pack.pk),
                "admin_theme_pack": str(admin_pack.pk),
            }
        )
        self.assertEqual(response.status_code, 200)
        payload = self.client.session.get(SESSION_KEY, {})
        self.assertEqual(payload.get("theme_pack"), site_pack.pk)
        self.assertEqual(payload.get("admin_theme_pack"), admin_pack.pk)
        self.assertIn("use_dark_mode", payload)
        self.assertIn("admin_use_site_primary", payload)
        self.assertFalse(payload.get("use_dark_mode"))
        self.assertFalse(payload.get("admin_use_site_primary"))
