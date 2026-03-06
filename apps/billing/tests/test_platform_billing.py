from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.billing.models import BillingAccount, PlatformLedgerEntry, TenantSubscription
from apps.billing.services import ensure_subscription_for_school, record_platform_charge
from apps.schools.models import School
from apps.siteconfig.models import Plan


class PlatformBillingServicesTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Platform Growth",
            slug="platform-growth",
            base_price=Decimal("199.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Billing School",
            slug="billing-school",
            subdomain="billing-school",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.FREE_TRIAL,
        )

    def test_ensure_subscription_creates_platform_billing_records(self):
        account, subscription, created = ensure_subscription_for_school(self.school)

        self.assertTrue(created)
        self.assertEqual(account.status, BillingAccount.Status.TRIAL)
        self.assertEqual(subscription.status, TenantSubscription.Status.TRIALING)
        self.assertEqual(subscription.plan, self.plan)
        self.assertEqual(subscription.base_amount, Decimal("199.00"))

    def test_record_platform_charge_creates_ledger_entry(self):
        ensure_subscription_for_school(self.school)

        entry = record_platform_charge(
            school=self.school,
            amount="149.50",
            description="March platform subscription",
            reference="INV-PLATFORM-001",
            source="billing_dashboard",
        )

        self.assertEqual(entry.entry_type, PlatformLedgerEntry.EntryType.CHARGE)
        self.assertEqual(entry.amount, Decimal("149.50"))
        self.assertEqual(entry.reference, "INV-PLATFORM-001")


class PlatformBillingDashboardTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Enterprise",
            slug="enterprise",
            base_price=Decimal("499.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Dashboard Billing School",
            slug="dashboard-billing-school",
            subdomain="dashboard-billing-school",
            is_active=True,
            plan=self.plan,
        )
        ensure_subscription_for_school(self.school)
        record_platform_charge(
            school=self.school,
            amount="499.00",
            description="First platform invoice",
            reference="INV-ENTERPRISE-001",
        )
        self.superuser = User.objects.create_user(
            username="billing-super",
            password="testpass123",
            is_superuser=True,
            is_staff=True,
        )

    def test_super_billing_dashboard_renders_platform_sections(self):
        self.client.force_login(self.superuser)
        response = self.client.get(reverse("super:billing_dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Platform billing")
        self.assertContains(response, "Dashboard Billing School")
        self.assertContains(response, "Recent platform ledger")
