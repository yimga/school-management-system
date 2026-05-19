from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.siteconfig.contrast_guard import remediate_brand_hex_on_background


class ThemeContrastRemediateTests(TestCase):
    def test_api_returns_remediated_hex(self):
        user = get_user_model().objects.create_superuser(
            username="theme_admin",
            email="theme@example.com",
            password="Test1234",
        )
        client = Client()
        client.force_login(user)
        url = reverse("siteconfig:api_brand_contrast_remediate")
        resp = client.post(
            url,
            data='{"brand_hex":"#ffff00","background_hex":"#ffffff","min_ratio":7}',
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("remediated_hex", body)
        self.assertTrue(
            remediate_brand_hex_on_background("#ffff00", "#ffffff", min_ratio=7.0)["ok"]
            or body.get("adjusted")
        )
