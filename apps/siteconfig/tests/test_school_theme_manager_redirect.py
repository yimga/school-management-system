"""Manager host must not reverse portal:* from school-theme (live preview / embed)."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from apps.schools.tests.manager_client import bind_manager_session, mark_manager_mfa_verified

_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["*", _MGR],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    SECURE_SSL_REDIRECT=False,
)
class SchoolThemeManagerRedirectTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            username="mgr_school_theme",
            password="testpass123",
            is_staff=True,
            is_superuser=True,
        )
        self.client = Client(HTTP_HOST=_MGR)
        self.client.force_login(self.user)
        bind_manager_session(self.client)
        mark_manager_mfa_verified(self.client)

    def test_school_theme_embed_redirects_to_theme_colors_not_portal(self):
        path = reverse("siteconfig:school_theme_settings") + "?embed=1"
        response = self.client.get(path, HTTP_HOST=_MGR, follow=False)
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertNotIn("/authentication/login/", location)
        self.assertIn("theme", location.lower())
        self.assertIn("embed=1", location)
