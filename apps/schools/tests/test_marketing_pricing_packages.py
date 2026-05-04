"""Pricing packages registry — honest PSP caveat and resolvable CTAs."""

import json
from pathlib import Path

from django.conf import settings
from django.test import Client, TestCase, override_settings
from django.urls import reverse


@override_settings(
    ALLOWED_HOSTS=["*"],
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
)
class MarketingPricingPackagesTests(TestCase):
    def test_package_data_loads(self):
        path = (
            Path(__file__).resolve().parent.parent
            / "data"
            / "pricing_packages.json"
        )
        data = json.loads(path.read_text(encoding="utf-8"))
        self.assertIn("packages", data)
        self.assertEqual(len(data["packages"]), 5)
        slugs = {p["slug"] for p in data["packages"]}
        self.assertEqual(
            slugs, {"starter", "growth", "professional", "enterprise", "network"}
        )

    def test_no_fake_unlimited_in_copy(self):
        path = (
            Path(settings.BASE_DIR)
            / "apps"
            / "schools"
            / "data"
            / "pricing_packages.json"
        )
        text = path.read_text(encoding="utf-8").lower()
        self.assertNotIn("unlimited settlement", text)
        self.assertNotIn("unlimited money", text)

    def test_page_includes_psp_caveat_and_ctas_resolve(self):
        client = Client()
        r = client.get(
            reverse("marketing_pricing_packages_clarity"),
            HTTP_HOST="runmycampus.com",
        )
        self.assertEqual(r.status_code, 200)
        body = r.content.decode("utf-8", errors="replace").lower()
        self.assertIn("psp", body)
        self.assertIn("merchant", body)
        reverse("marketing_contact")
        reverse("marketing_book_demo")
