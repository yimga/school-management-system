"""Tenant-scoped payment readiness dashboard (school + staff)."""

from __future__ import annotations

from unittest.mock import patch

from django.test import Client, RequestFactory, TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.finance.models import ComplianceProfile, PaymentGatewayHealthSnapshot
from apps.finance.payment_gateway_health import record_gateway_health_snapshots
from apps.finance.regional_payment_profiles import clear_profile_cache
from apps.finance.views_payment_readiness_dashboard import payment_readiness_dashboard
from apps.schools.models import School


class PaymentReadinessDashboardHttpTests(TestCase):
    def tearDown(self):
        clear_profile_cache()

    def setUp(self):
        self.school_a = School.objects.create(
            name="Tenant A",
            slug="tenant-a",
            subdomain="tenanta",
            is_active=True,
        )
        self.school_b = School.objects.create(
            name="Tenant B",
            slug="tenant-b",
            subdomain="tenantb",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name="CM Corridor",
            country_code="CM",
            currency_code="XAF",
            is_active=True,
        )
        self.staff = User.objects.create_user(
            username="staffpay",
            password="Pass_1234",
            email="staff@example.com",
            is_staff=True,
        )

    def test_anonymous_blocked_from_dashboard(self):
        url = reverse("finance:payment_readiness_dashboard")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (302, 403))

    def test_dashboard_403_without_school_context(self):
        factory = RequestFactory()
        request = factory.get("/finance/payment-readiness/")
        request.user = self.staff
        request.school = None
        with patch(
            "apps.finance.views_payment_readiness_dashboard._active_profile",
            return_value=self.profile,
        ):
            response = payment_readiness_dashboard(request)
        self.assertEqual(response.status_code, 403)

    def test_dashboard_200_with_school_and_staff(self):
        factory = RequestFactory()
        request = factory.get("/finance/payment-readiness/")
        request.user = self.staff
        request.school = self.school_a
        with patch(
            "apps.finance.views_payment_readiness_dashboard._active_profile",
            return_value=self.profile,
        ):
            response = payment_readiness_dashboard(request)
        self.assertEqual(response.status_code, 200)

    def test_tenant_cannot_see_other_school_health_messages(self):
        record_gateway_health_snapshots(
            self.school_b,
            [
                {
                    "rail_code": "X",
                    "provider_key": "p",
                    "status": "ready",
                    "message": "UNIQUE-TENANT-B-ONLY",
                    "action_required": "",
                }
            ],
        )
        factory = RequestFactory()
        request = factory.get("/finance/payment-readiness/")
        request.user = self.staff
        request.school = self.school_a
        with patch(
            "apps.finance.views_payment_readiness_dashboard._active_profile",
            return_value=self.profile,
        ):
            response = payment_readiness_dashboard(request)
        content = response.content.decode("utf-8")
        self.assertNotIn("UNIQUE-TENANT-B-ONLY", content)

    def test_snapshots_scoped_to_request_school_only(self):
        record_gateway_health_snapshots(
            self.school_b,
            [
                {
                    "rail_code": "MTN_MOMO",
                    "provider_key": "m",
                    "status": "ready",
                    "message": "B-msg",
                    "action_required": "",
                }
            ],
        )
        self.assertEqual(
            PaymentGatewayHealthSnapshot.objects.filter(school=self.school_a).count(),
            0,
        )
        self.assertGreater(
            PaymentGatewayHealthSnapshot.objects.filter(school=self.school_b).count(),
            0,
        )
