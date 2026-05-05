import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings


@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingPremiumStoryTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.host = "runmycampus.com"
        self.env = patch.dict(
            os.environ,
            {
                "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
                "MULTI_TENANT_LEGACY_BASE_DOMAINS": "",
            },
            clear=False,
        )
        self.env.start()
        self._funnel_patcher = patch(
            "apps.schools.funnel_events.record_marketing_funnel_event",
            lambda *args, **kwargs: None,
        )
        self._funnel_patcher.start()

    def tearDown(self):
        self._funnel_patcher.stop()
        self.env.stop()

    @patch("apps.schools.marketing_views.random.choice", side_effect=["A", "default"])
    def test_homepage_has_premium_shell_story_and_single_header_cta(self, _choice):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")

        self.assertIn("Offline-ready education operating system for modern schools.", body)
        self.assertIn("css/rmc-premium-os.css", body)
        self.assertIn('data-rmc-premium-shell="marketing"', body)
        self.assertIn('data-rmc-page-purpose="public-story"', body)
        self.assertIn("Book demo", body)
        self.assertIn("See product tour", body)
        self.assertNotIn('href="#"', body)
