"""
Public marketing story reset contract: hero, nav labels, honest trust posture, live routes.

SQLite tip: if ``--keepdb`` hits ``table already exists``, remove the file named by
``DJANGO_TEST_DB_FILE`` under ``.django_test_dbs/`` (or pick a new filename) and rerun.
"""

import os
from unittest.mock import patch

from django.test import Client, TestCase, override_settings
from django.urls import reverse

@override_settings(ALLOWED_HOSTS=["*"], DEBUG=False, SECURE_SSL_REDIRECT=False)
class MarketingPublicStoryResetTests(TestCase):
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
        # Avoid funnel INSERT noise; does not replace full DB setup but skips one write per visit.
        self._funnel_patcher = patch(
            "apps.schools.funnel_events.record_marketing_funnel_event",
            lambda *args, **kwargs: None,
        )
        self._funnel_patcher.start()

    def tearDown(self):
        self._funnel_patcher.stop()
        self.env.stop()

    @patch(
        "apps.schools.marketing_views.random.choice",
        side_effect=["A", "default"],
    )
    def test_homepage_hero_headline_and_no_fake_cert_snippets(self, _mock_choice):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("Run every school day from one operating system.", body)
        self.assertIn(
            "One quiet system behind admissions, classrooms, fees",
            body,
        )
        lowered = body.lower()
        self.assertNotIn("soc 2", lowered)
        self.assertNotIn("iso 27001", lowered)
        self.assertNotIn("soc2", lowered)

    def test_header_chrome_has_no_dummy_hash_href_and_book_demo(self):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        idx = body.find('id="marketingNav"')
        self.assertGreater(idx, 0)
        header_chunk = body[idx : idx + 12000]
        self.assertNotIn('href="#"', header_chunk)
        self.assertNotIn("href='#'", header_chunk)
        self.assertIn("Book demo", header_chunk)

    def test_trust_offline_payment_story_routes_resolve(self):
        for name in (
            "marketing_trust_dedicated",
            "marketing_story_offline_first",
            "marketing_story_payments_readiness",
            "marketing_resources_product_tour",
        ):
            with self.subTest(url_name=name):
                path = reverse(name)
                r = self.client.get(path, HTTP_HOST=self.host, follow=True)
                self.assertEqual(r.status_code, 200, f"GET {path}")

    def test_homepage_institution_strip_aligns_with_solution_stories(self):
        resp = self.client.get("/marketing/", HTTP_HOST=self.host)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("/solutions/private-schools/", body)
        self.assertIn("/for-school-networks/", body)
        self.assertIn("/roles/finance/", body)

    def test_inner_marketing_pages_render_hub_strip_not_full_chip_scroll(self):
        resp = self.client.get("/pricing/", HTTP_HOST=self.host, follow=True)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("marketing-hub-strip", body)
        self.assertNotIn('class="page-nav-scroll"', body)
