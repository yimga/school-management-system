"""Paid marketplace install requires billing readiness when enforcement flag is on."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase, override_settings

from apps.billing.models import BillingAccount
from apps.billing.services import ensure_billing_account_for_school
from apps.marketplace.models import (
    AppInstallation,
    MarketplaceApp,
    MarketplaceListing,
    PublisherOrganization,
)
from apps.marketplace.services import install_app
from apps.schools.models import School


class MonetizedInstallEnforcementTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Bill School",
            slug="bill-school",
            subdomain="bill-school",
            is_active=True,
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="pub-bill",
            name="Publisher Bill",
        )
        cls.paid_app = MarketplaceApp.objects.create(
            publisher=cls.publisher,
            slug="paid-enforce",
            app_key="paid-enforce",
            name="Paid Enforce",
            description="",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            version="1.0.0",
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
            price=Decimal("50.00"),
            billing_interval=MarketplaceApp.BillingInterval.MONTHLY,
        )
        MarketplaceListing.objects.create(
            app=cls.paid_app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            revenue_share_percent=Decimal("70.00"),
        )
        cls.free_app = MarketplaceApp.objects.create(
            publisher=cls.publisher,
            slug="free-enforce",
            app_key="free-enforce",
            name="Free Enforce",
            description="",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            version="1.0.0",
            manifest={"test": True},
            pricing_model=MarketplaceApp.PricingModel.FREE,
            is_intentionally_free=True,
        )
        MarketplaceListing.objects.create(
            app=cls.free_app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            revenue_share_percent=Decimal("70.00"),
        )

    @override_settings(MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING=True)
    def test_paid_install_fails_without_processor_customer(self):
        ensure_billing_account_for_school(self.school)
        acct = BillingAccount.objects.get(school=self.school)
        acct.external_customer_ref = ""
        acct.save(update_fields=["external_customer_ref", "updated_at"])
        before = AppInstallation.objects.filter(
            school=self.school, app=self.paid_app
        ).count()
        with self.assertRaises(RuntimeError):
            install_app(self.school, self.paid_app, skip_compatibility=True)
        after = AppInstallation.objects.filter(
            school=self.school, app=self.paid_app
        ).count()
        self.assertEqual(before, after)

    @override_settings(MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING=True)
    def test_paid_install_succeeds_with_processor_customer(self):
        ensure_billing_account_for_school(self.school)
        acct = BillingAccount.objects.get(school=self.school)
        acct.external_customer_ref = "cus_test_123"
        acct.save(update_fields=["external_customer_ref", "updated_at"])
        inst = install_app(self.school, self.paid_app, skip_compatibility=True)
        self.assertIsNotNone(inst.pk)

    @override_settings(MARKETPLACE_INSTALL_REQUIRES_PAID_BILLING=True)
    def test_free_app_install_without_customer(self):
        ensure_billing_account_for_school(self.school)
        acct = BillingAccount.objects.get(school=self.school)
        acct.external_customer_ref = ""
        acct.save(update_fields=["external_customer_ref", "updated_at"])
        inst = install_app(self.school, self.free_app, skip_compatibility=True)
        self.assertIsNotNone(inst.pk)
