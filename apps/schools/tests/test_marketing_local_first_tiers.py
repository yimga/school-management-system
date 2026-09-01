"""Tier 2–3 marketing: security annex, honest case studies, enterprise narrative."""

from pathlib import Path

from django.template import Context, Template
from django.test import Client, SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.schools.marketing_local_context import marketing_local_context
from apps.schools.security_packet_country_annex import (
    build_country_annex,
    country_code_for_jurisdiction,
    jurisdiction_choices,
)
from apps.siteconfig.tests._template_nodes import assert_wires

_BASE_MARKETING = Path("templates/marketing/base_marketing.html")


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
class MarketingLocalContextTemplateTests(SimpleTestCase):
    """Regression: marketing_local keys must not use leading underscores in templates."""

    def test_context_exposes_is_resolved_not_underscore_key(self):
        from django.test import RequestFactory

        req = RequestFactory().get("/", HTTP_HOST="runmycampus.com")
        ctx = marketing_local_context(req)["marketing_local"]
        self.assertIn("is_resolved", ctx)
        self.assertNotIn("_resolved", ctx)

    def test_base_marketing_uses_template_safe_is_resolved_key(self):
        text = Path("templates/marketing/base_marketing.html").read_text(encoding="utf-8")
        # Both of these are the {% if %} CONDITION itself -- template code, which
        # no parse and no render of the file can see -- so both stay source reads.
        self.assertIn("marketing_local.is_resolved", text)
        self.assertNotIn("marketing_local._resolved", text)
        # What the reads cannot tell is whether that {% if %} still guards
        # anything. It guards exactly one thing, the local-first band include, and
        # an {% include %} is what a parse CAN see.
        assert_wires(self, _BASE_MARKETING, "_local_first_band.html")
        # Compile the production {% if %}: Django rejects underscore-prefixed attrs.
        rendered = Template(
            "{% if marketing_local.country_code and marketing_local.is_resolved %}ok{% endif %}"
        ).render(
            Context(
                {
                    "marketing_local": {
                        "country_code": "US",
                        "is_resolved": True,
                    }
                }
            )
        )
        self.assertEqual(rendered, "ok")


@override_settings(
    MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    MULTI_TENANT_LEGACY_BASE_DOMAINS="",
    ALLOWED_HOSTS=["runmycampus.com", "testserver"],
)
class MarketingTierSurfaceTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_marketing_home_returns_200(self):
        resp = self.client.get("/", HTTP_HOST="runmycampus.com")
        self.assertEqual(resp.status_code, 200, msg=resp.content[:300])

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
