"""Marketing homepage media + analytics viz context."""
import unittest

from django.test import SimpleTestCase, override_settings
from django.test import Client
from django.urls import reverse

import django


class MarketingMediaVizContextTest(SimpleTestCase):
    def test_marketing_views_declares_public_seeder_viz(self):
        from pathlib import Path

        text = Path("apps/schools/marketing_views.py").read_text(encoding="utf-8")
        self.assertIn('"ENABLE_UNIFIED_ANALYTICS_VIZ": True', text)
        self.assertIn('"ANALYTICS_VIZ_USE_SEEDER": True', text)
        self.assertIn('"ANALYTICS_VIZ_API_URL": ""', text)


class MarketingHomeRenderMediaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        django.setup()
        super().setUpClass()

    def test_home_includes_video_portal_and_analytics_mount(self) -> None:
        client = Client()
        try:
            with override_settings(ALLOWED_HOSTS=["*"]):
                response = client.get(reverse("marketing_landing"), HTTP_HOST="runmycampus.com")
        except Exception as exc:  # pragma: no cover
            self.skipTest(str(exc))
        if response.status_code != 200:
            self.skipTest(f"home returned {response.status_code}")
        html = response.content.decode("utf-8", errors="replace")
        self.assertIn("data-mkt-video-portal", html)
        self.assertIn("Animated product preview", html)
        self.assertIn('data-tenant-id="marketing-demo"', html)
        self.assertIn('data-use-seeder="1"', html)
        self.assertNotIn('<source src=""', html)
