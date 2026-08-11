from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse

from apps.schools.models import School
from apps.schools.onboarding_recommendations import (
    MANIFEST_VERSION,
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
                "campus_count": 3,
                "staff_count": 180,
                "operating_model": "mixed",
                "operational_services": ["boarding", "transport", "clinic"],
                "connectivity_profile": "limited",
                "payment_profile": "multi-channel",
                "assessment_profile": "national",
                "identity_profile": "microsoft-sso",
                "data_residency_requirement": "regional",
                "accessibility_profile": "enhanced",
                "migration_complexity": "multi-system",
                "automation_preference": "automation-first",
                "migration_vendor": "powerschool",
                "migration_domains": ["students", "grades", "attendance"],
            },
        )
        rec = manifest["recommendations"]
        self.assertTrue(manifest["offline_safe"])
        self.assertEqual(rec["lms"], "moodle")
        self.assertEqual(rec["district"], "district-console")
        self.assertIn("fees-finance", rec["modules"])
        self.assertIn("advanced-analytics", rec["modules"])
        self.assertEqual(manifest["version"], MANIFEST_VERSION)
        self.assertEqual(manifest["confidence"], "high")
        self.assertTrue(all(card["reason"] for card in manifest["recommendation_cards"]))
        self.assertTrue(all(card["recommended"] for card in manifest["recommendation_cards"]))
        self.assertEqual(rec["blueprint"]["primary"]["key"], "multi-campus-network")
        self.assertEqual(rec["blueprint"]["primary"]["version"], "1.0.0")
        self.assertTrue(rec["blueprint"]["all_contracts_resolved"])
        self.assertEqual(rec["subscription_plan"], "campus-enterprise")
        self.assertIn("offline-sync", rec["modules"])
        self.assertIn("transport", rec["modules"])
        self.assertIn("health-safety", rec["modules"])
        self.assertIn("identity-federation", rec["modules"])
        self.assertIn("accessibility-assist", rec["modules"])
        self.assertIn("workflow-automation", rec["modules"])
        self.assertIn("guided-data-migration", rec["modules"])
        self.assertEqual(rec["migration"]["vendor"], "powerschool")
        self.assertEqual(rec["migration"]["domains"], ["students", "grades", "attendance"])
        self.assertFalse(manifest["subscription"]["auto_entitlement"])
        self.assertTrue(manifest["subscription"]["requires_confirmation"])

    def test_malformed_legacy_capacity_falls_back_safely(self):
        manifest = build_onboarding_recommendations(
            country_code="KE",
            institution_profile={"student_capacity": "not-a-number"},
        )
        self.assertEqual(manifest["profile"]["student_capacity"], 0)
        self.assertEqual(manifest["validation_issues"][0]["code"], "invalid_integer")

    def test_international_single_school_uses_versioned_catalog_contract(self):
        manifest = build_onboarding_recommendations(
            country_code="US",
            education_cycles=["high-school"],
            language_codes=["en", "es"],
            institution_profile={
                "organization_scope": "single",
                "assessment_profile": "international",
                "student_capacity": 800,
            },
        )
        blueprint = manifest["recommendations"]["blueprint"]
        self.assertEqual(blueprint["primary"]["key"], "international-school")
        self.assertIn("bilingual-school", [row["key"] for row in blueprint["overlays"]])
        self.assertFalse(manifest["subscription"]["auto_entitlement"])


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

    def test_changed_intent_refreshes_stale_manifest(self):
        school = School.objects.create(
            name="Changing School",
            slug="changing-recommendations",
            subdomain="changing-recommendations",
            country_code="CM",
            settings={
                "onboarding_intent": {
                    "institution_profile": {"organization_scope": "single"}
                }
            },
        )
        first = ensure_school_recommendations(school)
        school.settings["onboarding_intent"]["institution_profile"][
            "organization_scope"
        ] = "network"
        school.save(update_fields=["settings", "updated_at"])
        second = ensure_school_recommendations(school)
        self.assertNotEqual(first["fingerprint"], second["fingerprint"])
        self.assertEqual(
            second["recommendations"]["district"], "district-console"
        )

    def test_confirmed_manifest_is_preserved_and_changed_inputs_become_candidate(self):
        school = School.objects.create(
            name="Confirmed School",
            slug="confirmed-recommendations",
            subdomain="confirmed-recommendations",
            country_code="CM",
            settings={"onboarding_intent": {"institution_profile": {"organization_scope": "single"}}},
        )
        current = ensure_school_recommendations(school)
        current["review_state"]["confirmed"] = True
        school.settings["recommendation_manifest"] = current
        school.settings["onboarding_intent"]["institution_profile"]["organization_scope"] = "network"
        school.save(update_fields=["settings", "updated_at"])
        returned = ensure_school_recommendations(school)
        school.refresh_from_db()
        self.assertEqual(returned["fingerprint"], current["fingerprint"])
        self.assertEqual(
            school.settings["recommendation_candidate"]["review_state"]["status"],
            "changed-inputs-require-review",
        )


@override_settings(RATELIMIT_ENABLE=False, ROOT_URLCONF="config.public_urls", EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class SignupRecommendationCaptureTests(TestCase):
    def test_signup_persists_intent_and_recommendations(self):
        response = self.client.post(reverse("signup_school"), {
            "name": "Intent Academy", "slug": "intent-academy", "email": "owner@intent.test", "country_code": "CM",
            "school_type": ["secondary"], "language_codes": ["en"], "primary_language_code": "en",
            "funding_type": "mission", "organization_scope": "network", "student_capacity": "1500", "lms_preference": "moodle",
            "campus_count": "3", "staff_count": "180", "operating_model": "mixed",
            "operational_services": ["boarding", "transport", "clinic"],
            "connectivity_profile": "limited", "payment_profile": "multi-channel", "go_live_timeline": "30-days",
            "assessment_profile": "national", "identity_profile": "microsoft-sso",
            "data_residency_requirement": "regional", "accessibility_profile": "enhanced",
            "migration_complexity": "multi-system", "automation_preference": "automation-first",
            "migration_vendor": "powerschool", "migration_domains": ["students", "grades"],
        })
        self.assertEqual(response.status_code, 200)
        school = School.objects.get(slug="intent-academy")
        self.assertEqual(school.settings["onboarding_intent"]["institution_profile"]["student_capacity"], 1500)
        self.assertEqual(school.settings["recommendation_manifest"]["recommendations"]["lms"], "moodle")
        profile = school.settings["onboarding_intent"]["institution_profile"]
        self.assertEqual(profile["campus_count"], 3)
        self.assertEqual(profile["connectivity_profile"], "limited")
        self.assertEqual(profile["migration_vendor"], "powerschool")
        self.assertEqual(profile["migration_domains"], ["students", "grades"])
        self.assertEqual(profile["operational_services"], ["boarding", "transport", "clinic"])
        self.assertEqual(profile["assessment_profile"], "national")
        self.assertEqual(profile["identity_profile"], "microsoft-sso")
        self.assertEqual(profile["migration_complexity"], "multi-system")
        self.assertEqual(
            school.settings["recommendation_manifest"]["recommendations"]["migration"]["domains"],
            ["students", "grades"],
        )
        self.assertEqual(
            school.settings["recommendation_manifest"]["subscription"]["recommended_slug"],
            "campus-enterprise",
        )

    def test_signup_rejects_invalid_optional_profile_values_without_creating_school(self):
        response = self.client.post(
            reverse("signup_school"),
            {
                "name": "Invalid Profile Academy",
                "slug": "invalid-profile-academy",
                "email": "owner@invalid-profile.test",
                "country_code": "CM",
                "organization_scope": "unbounded",
                "learner_scale": "millions",
                "student_capacity": "not-a-number",
                "operational_services": ["unknown-service"],
            },
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(School.objects.filter(slug="invalid-profile-academy").exists())
        codes = " ".join(response.json()["errors"]).lower()
        self.assertIn("supported value", codes)
        self.assertIn("whole number", codes)
