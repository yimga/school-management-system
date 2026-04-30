"""Marketplace monetization hooks (pricing fields, install ledger + earnings split)."""

from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from apps.billing.models import PlatformLedgerEntry
from apps.marketplace.services import install_app
from apps.marketplace.models import (
    MarketplaceApp,
    MarketplaceListing,
    PlatformMarketplaceEarning,
    PublisherOrganization,
    TenantMarketplaceSubscription,
)
from apps.schools.models import School


class MarketplaceMonetizationTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Mon School",
            slug="mon-school",
            subdomain="mon-school",
            is_active=True,
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="pub-mon",
            name="Publisher Mon",
        )
        cls.app = MarketplaceApp.objects.create(
            publisher=cls.publisher,
            slug="paid-app",
            app_key="paid-app",
            name="Paid App",
            description="",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            version="1.0.0",
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
            price=Decimal("100.00"),
            billing_interval=MarketplaceApp.BillingInterval.MONTHLY,
        )
        MarketplaceListing.objects.create(
            app=cls.app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            revenue_share_percent=Decimal("70.00"),
        )

    @override_settings(MARKETPLACE_PLATFORM_FEE_PERCENT="20")
    def test_install_creates_subscription_ledger_and_platform_earning(self):
        inst = install_app(
            school=self.school,
            app=self.app,
            installed_by=None,
            skip_compatibility=True,
        )
        self.assertTrue(
            TenantMarketplaceSubscription.objects.filter(installation=inst).exists()
        )
        self.assertTrue(
            PlatformLedgerEntry.objects.filter(
                source="marketplace_app_install",
                school=self.school,
            ).exists()
        )
        earning = PlatformMarketplaceEarning.objects.filter(
            installation=inst,
            gross_amount=Decimal("100.00"),
        ).first()
        self.assertIsNotNone(earning)
        assert earning is not None
        self.assertEqual(earning.platform_fee_amount, Decimal("20.00"))
        self.assertEqual(earning.publisher_share_amount, Decimal("56.00"))

    def test_free_pricing_requires_intentional_flag_in_clean(self):
        app = MarketplaceApp(
            publisher=self.publisher,
            slug="free-intent",
            app_key="free-intent",
            name="Free Intent",
            description="",
            kind=MarketplaceApp.AppKind.FIRST_PARTY,
            version="1.0.0",
            # Non-empty JSON: Django JSONField treats {} as blank when blank=False on the field.
            manifest={"test": True},
            pricing_model=MarketplaceApp.PricingModel.FREE,
            is_intentionally_free=False,
        )
        with self.assertRaises(ValidationError):
            app.full_clean()
        app.is_intentionally_free = True
        app.full_clean()
