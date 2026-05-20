"""Tier 2–3 marketing: security annex, honest case studies, enterprise narrative."""

from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.schools.security_packet_country_annex import (
    build_country_annex,
    country_code_for_jurisdiction,
    jurisdiction_choices,
)


class SecurityPacketCountryAnnexTests(SimpleTestCase):
    def test_jurisdiction_maps_to_country(self):
        self.assertEqual(country_code_for_jurisdiction("ndpr-ng"), "NG")
        self.assertEqual(country_code_for_jurisdiction("pipeda-ca"), "CA")

    def test_build_country_annex_ng_preset(self):
        annex = build_country_annex(country_code="NG")
        self.assertEqual(annex["country_code"], "NG")
        self.assertIn("Nigeria", annex["profile_name"])
        self.assertEqual(annex["currency_code"], "NGN")

    def test_jurisdiction_choices_non_empty(self):
        self.assertGreaterEqual(len(jurisdiction_choices()), 8)


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    MULTI_TENANT_LEGACY_BASE_DOMAINS="",
    ALLOWED_HOSTS=["runmycampus.com", "testserver"],
)
class MarketingTierSurfaceTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_security_packet_renders_jurisdiction_and_annex(self):
        resp = self.client.get(
            reverse("marketing_security_packet_request"),
            {"jurisdiction": "ndpr-ng"},
            HTTP_HOST="runmycampus.com",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("data-mkt-security-country-annex", body)
        self.assertIn("Which jurisdiction governs your student records", body)
        self.assertIn("Nigeria", body)

    def test_case_studies_honest_labels_not_school_a(self):
        resp = self.client.get(
            "/resources/case-studies/",
            HTTP_HOST="runmycampus.com",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("data-mkt-case-studies-honest", body)
        self.assertIn("Cameroon", body)
        self.assertNotIn('"School A"', body)

    def test_demo_form_jurisdiction_label(self):
        resp = self.client.get(
            reverse("marketing_demo"),
            HTTP_HOST="runmycampus.com",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Which jurisdiction governs your student records", resp.content)

    def test_pricing_enterprise_governance_narrative(self):
        resp = self.client.get(
            "/pricing/",
            HTTP_HOST="runmycampus.com",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("governance layer", body)

    def test_marketplace_per_campus_language(self):
        resp = self.client.get(
            "/grow/marketplace/",
            HTTP_HOST="runmycampus.com",
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode()
        self.assertIn("activate per campus", body.lower())

    def test_landing_scale_illustrative_disclaimer(self):
        resp = self.client.get(
            reverse("marketing_landing"),
            HTTP_HOST="runmycampus.com",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertIn(b"Illustrative scale signal", resp.content)
