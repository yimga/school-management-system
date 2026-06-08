from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.billing.models import BillingAccount, TenantSubscription
from apps.schools.models import School


class StudioOSBillingSummaryTests(TestCase):
    def setUp(self):
        # Superuser bypasses ModuleAccessMiddleware for integrations_marketplace
        # (unknown module namespace is default-deny for staff-only users).
        self.staff = User.objects.create_user(
            username="billing.operator",
            is_staff=True,
            is_superuser=True,
        )
        self.client.force_login(self.staff)
        self.school = School.objects.create(
            name="Billing Summary School",
            slug="billing-summary-school",
            subdomain="billing-summary-school",
        )
        self.account = BillingAccount.objects.create(
            school=self.school,
            currency_code="USD",
        )

    def test_summary_uses_live_subscription_aggregates(self):
        TenantSubscription.objects.create(
            billing_account=self.account,
            school=self.school,
            status=TenantSubscription.Status.TRIALING,
            billing_cycle=TenantSubscription.BillingCycle.MONTHLY,
            base_amount=Decimal("20.00"),
            addons_amount=Decimal("5.00"),
            trial_end_date=timezone.localdate() + timedelta(days=3),
            metadata={"dunning_attempts": 3},
        )
        other_school = School.objects.create(
            name="Annual Billing School",
            slug="annual-billing-school",
            subdomain="annual-billing-school",
        )
        other_account = BillingAccount.objects.create(
            school=other_school,
            currency_code="USD",
        )
        TenantSubscription.objects.create(
            billing_account=other_account,
            school=other_school,
            status=TenantSubscription.Status.ACTIVE,
            billing_cycle=TenantSubscription.BillingCycle.ANNUAL,
            base_amount=Decimal("120.00"),
        )

        response = self.client.get(
            reverse("integrations_marketplace:s10x_billing_summary")
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["active_subscription_count"], 2)
        self.assertEqual(payload["monthly_revenue_by_currency"], {"USD": "35.00"})
        self.assertEqual(payload["trial_expiring_7d_count"], 1)
        self.assertEqual(payload["dunning_failed_3plus_count"], 1)
