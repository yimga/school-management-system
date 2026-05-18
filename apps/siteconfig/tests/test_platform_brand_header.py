"""Platform brand mark and manager header regression tests."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import Client, TestCase, override_settings

User = get_user_model()

_MGR = "manager.runmycampus.com"


@override_settings(
    ALLOWED_HOSTS=["testserver", "127.0.0.1", "localhost", _MGR, "*"],
    ROOT_URLCONF="config.manager_urls",
)
class PlatformBrandHeaderTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(
            username="brand_header_admin",
            password="x" * 12,
            role=User.Role.SUPERADMIN,
            is_staff=True,
            is_superuser=True,
        )

    def test_platform_wordmark_partial_renders_navy_gold_split(self):
        html = render_to_string(
            "components/rmc_brand_mark.html",
            {
                "wordmark_style": "platform",
                "variant": "lockup",
                "size": 32,
                "label": "RunMyCampus",
                "surface_badge": "Manager",
            },
        )
        self.assertIn('data-rmc-brand-mark="1"', html)
        self.assertIn("rmc-brand-mark__title--platform", html)
        self.assertIn("rmc-brand-word--navy", html)
        self.assertIn("rmc-brand-word--gold", html)
        self.assertIn("RUN", html)
        self.assertIn("MY", html)
        self.assertIn("CAMPUS", html)

    def test_manager_super_dashboard_renders_platform_brand_markers(self):
        client = Client(HTTP_HOST=_MGR, raise_request_exception=False)
        client.force_login(self.user)
        response = client.get("/super/")
        self.assertEqual(response.status_code, 200, msg=response.content[:400])
        body = response.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-brand-mark="1"', body)
        self.assertIn("rmc-brand-mark__title--platform", body)
        self.assertIn("rmc-brand-word--navy", body)
        self.assertIn("rmc-brand-word--gold", body)
        self.assertIn('data-rmc-platform-header="manager"', body)
        self.assertIn("rmc-control-plane-chrome", body)
        self.assertIn("cpSearchInput", body)