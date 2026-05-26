"""Wind-down blocks finance enrollment and commerce writes."""

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from apps.lifecycle.wind_down import apply_wind_down_mode
from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce
from apps.schools.models import School

User = get_user_model()


class WindDownCommerceGuardTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Guard School",
            slug="guard-school",
            subdomain="guard-school",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username="guard-admin",
            email="guard@example.com",
            password="test-pass-123",
            role="ADMIN",
        )

    def test_block_generate_fees_post(self):
        apply_wind_down_mode(self.school, note="test")
        self.school.refresh_from_db()
        request = self.factory.post("/finance/fees/generate/")
        request.user = self.user
        request.school = self.school
        blocked = block_if_wind_down_commerce(request)
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked.status_code, 403)

    def test_block_cash_office_closure_post(self):
        apply_wind_down_mode(self.school, note="test")
        self.school.refresh_from_db()
        request = self.factory.post("/finance/cash-office/closure/")
        request.user = self.user
        request.school = self.school
        blocked = block_if_wind_down_commerce(request)
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked.status_code, 403)

    def test_block_offline_payment_intent_approve_post(self):
        apply_wind_down_mode(self.school, note="test")
        request = self.factory.post("/finance/offline/approve/1/")
        request.user = self.user
        request.school = self.school
        blocked = block_if_wind_down_commerce(request)
        self.assertIsNotNone(blocked)
        self.assertEqual(blocked.status_code, 403)

    def test_redirect_after_operator_create_builds_urls(self):
        from apps.lifecycle.wind_down_guards import redirect_after_operator_school_create

        request = self.factory.get("/super/schools/rapid/")
        request.user = self.user
        request.META["HTTP_HOST"] = "localhost:8000"
        response = redirect_after_operator_school_create(request, self.school)
        self.assertEqual(response.status_code, 302)
        self.assertIn("lifecycle", response.url)
