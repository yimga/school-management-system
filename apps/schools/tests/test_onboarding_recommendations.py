from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School
from apps.schools.onboarding_recommendations import (
    build_onboarding_recommendations,
    ensure_school_recommendations,
)


class RecommendationRulesTests(SimpleTestCase):
    def test_network_secondary_profile_is_explainable_and_offline_safe(self):
        manifest = build_onboarding_recommendations(
            country_code="CM",
            education_cycles=["secondary", "tvet"],
            language_codes=["en", "fr"],
            institution_profile={
                "funding_type": "mission",
                "organization_scope": "network",
                "student_capacity": 1500,
                "lms_preference": "moodle",
            },
        )
        rec = manifest["recommendations"]
        self.assertTrue(manifest["offline_safe"])
        self.assertEqual(rec["lms"], "moodle")
        self.assertEqual(rec["district"], "district-console")
        self.assertIn("fees-finance", rec["modules"])
        self.assertIn("advanced-analytics", rec["modules"])


class RecommendationGrandfatherTests(TestCase):
    def test_existing_school_gets_manifest_without_overwriting_settings(self):
        school = School.objects.create(
            name="Legacy School",
            slug="legacy-recommendations",
            subdomain="legacy-recommendations",
            country_code="CM",
            settings={"legacy_choice": "keep-me"},
        )
        manifest = ensure_school_recommendations(school)
        school.refresh_from_db()
        self.assertEqual(school.settings["legacy_choice"], "keep-me")
        self.assertEqual(school.settings["recommendation_manifest"], manifest)


@override_settings(RATELIMIT_ENABLE=False, ROOT_URLCONF="config.public_urls", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SignupRecommendationCaptureTests(TestCase):
    def test_signup_persists_intent_and_recommendations(self):
        response = self.client.post(reverse("signup_school"), {
            "name": "Intent Academy", "slug": "intent-academy", "email": "owner@intent.test", "country_code": "CM",
            "school_type": ["secondary"], "language_codes": ["en"], "primary_language_code": "en",
            "funding_type": "mission", "organization_scope": "network", "student_capacity": "1500", "lms_preference": "moodle",
        })
        self.assertEqual(response.status_code, 200)
        school = School.objects.get(slug="intent-academy")
        self.assertEqual(school.settings["onboarding_intent"]["institution_profile"]["student_capacity"], 1500)
        self.assertEqual(school.settings["recommendation_manifest"]["recommendations"]["lms"], "moodle")
