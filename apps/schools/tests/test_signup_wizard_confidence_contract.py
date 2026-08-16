from pathlib import Path
import json
from unittest.mock import patch

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from apps.schools.onboarding_recommendations import build_onboarding_recommendations
from apps.schools.signup_views import signup_journey_event, signup_recommendations_preview


class RecommendationConfidenceEnvelopeTests(SimpleTestCase):
    def test_incomplete_answers_never_claim_high_confidence(self):
        manifest = build_onboarding_recommendations(country_code="CM")
        envelope = manifest["confidence_envelope"]
        self.assertFalse(envelope["high_confidence_eligible"])
        self.assertNotEqual(envelope["label"], "high")
        self.assertTrue(envelope["missing_critical_evidence"])
        self.assertEqual(
            envelope["score_kind"],
            "recommendation-readiness-not-prediction-probability",
        )
        self.assertFalse(envelope["calibration"]["statistical_probability"])

    def test_complete_consistent_registry_profile_can_cross_ninety(self):
        manifest = build_onboarding_recommendations(
            country_code="CM",
            education_cycles=["secondary"],
            language_codes=["en"],
            institution_profile={
                "funding_type": "private",
                "organization_scope": "single",
                "learner_scale": "1000-4999",
                "student_capacity": 1500,
                "operating_model": "day",
                "connectivity_profile": "offline-first",
                "migration_complexity": "none",
            },
        )
        envelope = manifest["confidence_envelope"]
        self.assertGreaterEqual(envelope["overall_score"], 90)
        self.assertTrue(envelope["high_confidence_eligible"])
        self.assertEqual(envelope["missing_critical_evidence"], [])
        self.assertEqual(envelope["registry_status"], "resolved")


@override_settings(RATELIMIT_ENABLE=False, ROOT_URLCONF="config.public_urls")
class SignupRecommendationPreviewTests(SimpleTestCase):
    def test_preview_uses_canonical_engine_and_exposes_evidence(self):
        request = RequestFactory().get(
            reverse("signup_recommendations_preview"), {
                "country_code": "CM",
                "school_type": "secondary",
                "language_codes": "en",
                "funding_type": "private",
                "organization_scope": "single",
                "learner_scale": "1000-4999",
                "student_capacity": "1500",
                "operating_model": "day",
                "connectivity_profile": "offline-first",
                "migration_complexity": "none",
            },
        )
        response = signup_recommendations_preview(request)
        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.content)
        self.assertTrue(payload["ok"])
        self.assertIn("confidence", payload)
        self.assertIn("components", payload["confidence"])
        self.assertIn("recommendations", payload)
        self.assertEqual(response["Cache-Control"], "private, max-age=60")

    def test_signup_page_binds_five_stage_progressive_wizard(self):
        html = (Path(settings.BASE_DIR) / "templates/schools/signup_school.html").read_text(encoding="utf-8")
        self.assertIn('data-rmc-signup-wizard="1"', html)
        self.assertEqual(html.count("data-rmc-wizard-step-indicator="), 5)
        self.assertIn("signup_recommendations_preview", html)
        self.assertIn("signup_journey_event", html)

    @patch("apps.schools.funnel_events.record_marketing_funnel_event")
    def test_journey_event_accepts_only_bounded_non_pii_categories(self, record):
        request = RequestFactory().post(
            reverse("signup_journey_event"), {"stage": "3", "action": "continue", "email": "must-not-be-recorded@example.test"}
        )
        response = signup_journey_event(request)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(record.call_args.args[0], "signup_journey")
        metadata = record.call_args.kwargs["metadata"]
        self.assertEqual(metadata, {"journey_version": 4, "stage": 3, "action": "continue"})
        self.assertNotIn("email", metadata)

    def test_journey_event_rejects_free_form_actions(self):
        request = RequestFactory().post(
            reverse("signup_journey_event"), {"stage": "2", "action": "user typed private content"}
        )
        response = signup_journey_event(request)
        self.assertEqual(response.status_code, 400)


class SignupWizardStaticContractTests(SimpleTestCase):
    def test_local_first_draft_and_review_contract_are_real(self):
        base = Path(settings.BASE_DIR)
        source = (base / "static/js/rmc-signup-wizard-v4.js").read_text(
            encoding="utf-8"
        )
        template = (base / "templates/schools/signup_school.html").read_text(
            encoding="utf-8"
        )
        css = (base / "static/css/rmc-signup-balanced-v3.css").read_text(
            encoding="utf-8"
        )
        for marker in (
            'indexedDB.open("rmc-signup-drafts"',
            'name: "AES-GCM"',
            "navigator.onLine",
            "dataset.rmcSignupReview",
            "missing_critical_evidence",
            "high_confidence_eligible",
            "panels.slice(1).findIndex",
            "validatePanel(panels[invalidStep + 1])",
            "Secure device drafts are unavailable",
            'if (queuedSubmission) emitJourney(current, "submit-queued")',
            'countryRow.classList.add("rmc-signup-identity-locality")',
            "STEP_GUIDANCE",
            "rmc-signup-wizard-panel__workspace",
            "data-rmc-step-completion",
            'size(directField("name"), "wide")',
            'size(directField("slug"), "standard")',
        ):
            self.assertIn(marker, source)
        self.assertIn("rmc-signup-wizard-v4.js", template)
        self.assertIn("rmc-signup-confidence-breakdown", css)
        self.assertIn(".rmc-signup-identity-locality", css)
        self.assertIn(".rmc-signup-wizard-panel__workspace", css)
        self.assertIn('[data-rmc-wizard-width="wide"]', css)
        self.assertIn('[data-rmc-wizard-width="standard"]', css)
        self.assertNotIn(
            '.rmc-signup-wizard-panel__body > [data-rmc-signup-field="migration_domains"],',
            css,
        )
        self.assertIn("prefers-reduced-motion", source)
