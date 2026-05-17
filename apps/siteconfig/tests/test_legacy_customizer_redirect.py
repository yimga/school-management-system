"""Legacy /siteconfig/customizer/ routes to Theme & Experience on manager, Studio on tenant."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

_MGR = "manager.runmycampus.com"
_TENANT = "demo.runmycampus.com"


@override_settings(ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR, _TENANT])
class LegacyCustomizerRedirectTests(TestCase):
    databases = {"default"}

    def test_manager_customizer_redirects_to_theme_colors(self):
        User = get_user_model()
        User.objects.create_user(
            username="cust_mgr",
            password="x" * 8,
            is_staff=True,
            is_superuser=True,
        )
        client = Client(HTTP_HOST=_MGR)
        client.login(username="cust_mgr", password="x" * 8)
        resp = client.get("/siteconfig/customizer/", follow=False)
        self.assertEqual(resp.status_code, 302)
        loc = resp["Location"]
        self.assertIn("/siteconfig/theme-colors/", loc)
        self.assertIn("standalone=1", loc)
