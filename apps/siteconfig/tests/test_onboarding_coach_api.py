import json
from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase, override_settings

from apps.schools.models import School
from apps.siteconfig.views_onboarding_coach import api_onboarding_coach

User = get_user_model()


@override_settings(AI_GATEWAY_ENABLED=False)
class OnboardingCoachApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Coach School",
            slug="coach-school",
            subdomain="coach-school",
            country_code="CM",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="coach_staff",
            password="x",
            email="c@example.com",
        )
        self.staff.role = "ADMIN"
        self.staff.is_staff = True
        self.staff.save(update_fields=["role", "is_staff"])
        self.user = User.objects.create_user(
            username="plain_user",
            password="x",
            email="p@example.com",
        )

    def test_staff_with_school_returns_coach_payload(self):
        rf = RequestFactory()
        req = rf.get("/siteconfig/api/onboarding-coach/")
        req.user = self.staff
        req.school = self.school
        resp = api_onboarding_coach(req)
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertTrue(data.get("ok"))
        self.assertIn("coach_message", data)
        self.assertIsInstance(data.get("quick_actions"), list)
        self.assertIn("source", data)

    def test_non_staff_forbidden(self):
        rf = RequestFactory()
        req = rf.get("/siteconfig/api/onboarding-coach/")
        req.user = self.user
        req.school = self.school
        resp = api_onboarding_coach(req)
        self.assertEqual(resp.status_code, 403)

    def test_no_school_forbidden(self):
        # The view resolves the school from the request and returns a UNIFIED 403
        # for both "no school context" and "cannot access tenant lifecycle" — a
        # single security-conscious forbidden response that doesn't leak whether a
        # school context exists (see api_onboarding_coach: `school is None or not
        # can_access_tenant_lifecycle(...)` → 403).
        rf = RequestFactory()
        req = rf.get("/siteconfig/api/onboarding-coach/")
        req.user = self.staff
        req.school = None
        resp = api_onboarding_coach(req)
        self.assertEqual(resp.status_code, 403)

    @override_settings(AI_GATEWAY_ENABLED=True)
    @patch("services.ai_gateway.invoke")
    @patch("apps.setup_studio.services.get_setup_studio_payload")
    def test_ai_gateway_path_passes_full_metadata(
        self,
        mock_payload,
        mock_invoke,
    ):
        mock_payload.return_value = {
            "health_summary": {"score": 72},
            "recommended_next": {"label": "Branding"},
            "steps": [],
            "launch_ready": False,
        }
        mock_invoke.return_value = (
            "Complete branding first, then verify imports before opening the portal.",
            {"provider": "ollama"},
        )

        rf = RequestFactory()
        req = rf.get("/siteconfig/api/onboarding-coach/")
        req.user = self.staff
        req.school = self.school

        resp = api_onboarding_coach(req)

        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        self.assertEqual(data.get("source"), "ai")
        self.assertIn("branding", data.get("coach_message", "").lower())
        metadata = mock_invoke.call_args.kwargs["metadata"]
        self.assertIs(metadata.get("request"), req)
        self.assertEqual(metadata.get("school"), self.school)
        self.assertEqual(metadata.get("school_id"), str(self.school.pk))
        self.assertEqual(metadata.get("tenant_id"), str(self.school.pk))
        self.assertEqual(metadata.get("user_id"), str(self.staff.pk))
        self.assertEqual(metadata.get("role"), "ADMIN")
        self.assertEqual(metadata.get("country_code"), "CM")

    @override_settings(AI_GATEWAY_ENABLED=True)
    @patch("services.ai_gateway.invoke")
    @patch("apps.setup_studio.services.get_setup_studio_payload")
    def test_ai_gateway_path_uses_school_pk_when_id_attribute_is_missing(
        self,
        mock_payload,
        mock_invoke,
    ):
        mock_payload.return_value = {
            "health_summary": {"score": 72},
            "recommended_next": {"label": "Branding"},
            "steps": [],
            "launch_ready": False,
        }
        mock_invoke.return_value = (
            "Complete branding first, then verify imports before opening the portal.",
            {"provider": "ollama"},
        )

        rf = RequestFactory()
        req = rf.get("/siteconfig/api/onboarding-coach/")
        req.user = self.staff
        req.school = SimpleNamespace(
            pk="school-pk-only",
            country_code="CM",
            default_region=SimpleNamespace(code="GB"),
        )

        resp = api_onboarding_coach(req)

        self.assertEqual(resp.status_code, 200)
        metadata = mock_invoke.call_args.kwargs["metadata"]
        self.assertEqual(metadata.get("school_id"), "school-pk-only")
        self.assertEqual(metadata.get("tenant_id"), "school-pk-only")
        self.assertEqual(metadata.get("country_code"), "CM")
