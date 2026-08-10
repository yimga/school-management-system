"""Endpoint + signup-capture tests for the progressive decision model.

Covers the live preview endpoint (recommended flags recomputed server-side),
the setup form capturing the new nuance dimensions into the versioned intent,
and the setup page rendering the decision block without error.
"""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School

_PUBLIC = dict(
    RATELIMIT_ENABLE=False,
    ROOT_URLCONF="config.public_urls",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
)


@override_settings(**_PUBLIC)
class DecisionsPreviewEndpointTests(TestCase):
    def _get(self, **params):
        resp = self.client.get(reverse("signup_decisions_preview"), params)
        self.assertEqual(resp.status_code, 200)
        return resp.json()

    def test_endpoint_flags_exactly_one_recommended_option_per_decision(self):
        model = self._get(country_code="CM", cycles="secondary")
        self.assertTrue(model["dimensions"])
        for dim in model["dimensions"]:
            flagged = [o for o in dim["options"] if o["recommended"]]
            self.assertEqual(len(flagged), 1, dim["key"])
            self.assertEqual(flagged[0]["value"], dim["recommended_value"])

    def test_endpoint_auto_applies_offline_first_for_limited_market(self):
        model = self._get(country_code="CM", cycles="secondary")
        conn = next(d for d in model["dimensions"] if d["key"] == "connectivity_profile")
        self.assertEqual(conn["recommended_value"], "limited")
        self.assertFalse(conn["ask"])
        self.assertIn("connectivity_profile", model["auto_keys"])

    def test_endpoint_reflects_funding_in_payment_recommendation(self):
        model = self._get(country_code="KE", cycles="secondary", funding="private")
        pay = next(d for d in model["dimensions"] if d["key"] == "payment_profile")
        self.assertEqual(pay["recommended_value"], "multi-channel")


@override_settings(**_PUBLIC)
class SignupCapturesNewDimensionsTests(TestCase):
    def test_signup_persists_new_dimensions_and_flows_to_manifest(self):
        resp = self.client.post(reverse("signup_school"), {
            "name": "Nuance Academy", "slug": "nuance-academy",
            "email": "owner@nuance.test", "country_code": "CM",
            "school_type": ["secondary"], "language_codes": ["en"],
            "primary_language_code": "en", "funding_type": "private",
            "session_pattern": "double", "curriculum_board": "ib",
            "governance_profile": "strict",
        })
        self.assertEqual(resp.status_code, 200)
        school = School.objects.get(slug="nuance-academy")
        profile = school.settings["onboarding_intent"]["institution_profile"]
        self.assertEqual(profile["session_pattern"], "double")
        self.assertEqual(profile["curriculum_board"], "ib")
        self.assertEqual(profile["governance_profile"], "strict")
        modules = school.settings["recommendation_manifest"]["recommendations"]["modules"]
        self.assertIn("international-curriculum", modules)
        self.assertIn("multi-session-timetable", modules)
        self.assertIn("compliance-governance", modules)

    def test_signup_rejects_unknown_dimension_codes(self):
        resp = self.client.post(reverse("signup_school"), {
            "name": "Guard Academy", "slug": "guard-academy",
            "email": "owner@guard.test", "country_code": "CM",
            "school_type": ["secondary"], "language_codes": ["en"],
            "primary_language_code": "en",
            "session_pattern": "wat", "governance_profile": "ultra",
        })
        self.assertEqual(resp.status_code, 200)
        profile = School.objects.get(slug="guard-academy").settings[
            "onboarding_intent"]["institution_profile"]
        self.assertEqual(profile["session_pattern"], "single")     # fell back
        self.assertEqual(profile["governance_profile"], "standard")  # fell back

    def test_setup_page_renders_decision_block(self):
        resp = self.client.get(reverse("signup_school"), {"country_code": "CM"})
        self.assertEqual(resp.status_code, 200)
        html = resp.content.decode()
        self.assertIn("data-rmc-decisions", html)
        self.assertIn('name="connectivity_profile"', html)
        self.assertIn("dec_governance_profile", html)
        self.assertIn("Recommended", html)
