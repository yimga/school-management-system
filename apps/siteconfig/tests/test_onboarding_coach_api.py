import json

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
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])
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

    def test_no_school_bad_request(self):
        rf = RequestFactory()
        req = rf.get("/siteconfig/api/onboarding-coach/")
        req.user = self.staff
        req.school = None
        resp = api_onboarding_coach(req)
        self.assertEqual(resp.status_code, 400)
