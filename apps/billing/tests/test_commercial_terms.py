from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.billing.models import (
    BillingPromotion,
    CountryBillingProfile,
    PlatformLedgerEntry,
    SubscriptionGrant,
    TenantSubscription,
)
from apps.billing.services import (
    apply_promotion_to_subscription,
    apply_subscription_waiver,
    ensure_subscription_for_school,
    platform_account_balance,
    preview_subscription_commercial_terms,
    run_platform_billing_lifecycle,
)
from apps.schools.models import School
from apps.siteconfig.models import CountryMultiplier, Plan, PlanAddon


class SubscriptionCommercialTermsTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Commercial Pro",
            slug="commercial-pro",
            base_price=Decimal("200.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Commercial School",
            slug="commercial-school",
            subdomain="commercial-school",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.REGULAR,
        )

    def test_waiver_preview_reduces_net_to_zero(self):
        _account, subscription, _ = ensure_subscription_for_school(self.school)
        apply_subscription_waiver(
            self.school,
            days=365,
            reason="Founder pilot",
        )

        terms = preview_subscription_commercial_terms(subscription)

        self.assertEqual(terms["gross_amount"], Decimal("200.00"))
        self.assertEqual(terms["waiver_amount"], Decimal("200.00"))
        self.assertEqual(terms["net_amount"], Decimal("0.00"))
        self.assertEqual(len(terms["applied_grants"]), 1)

    def test_lifecycle_posts_gross_charge_and_waiver_credit(self):
        account, subscription, _ = ensure_subscription_for_school(self.school)
        apply_subscription_waiver(
            self.school,
            days=365,
            reason="One-year launch waiver",
        )
        anchor = timezone.now() - timedelta(days=35)
        subscription.status = TenantSubscription.Status.ACTIVE
        subscription.current_period_start = anchor
        subscription.current_period_end = anchor + timedelta(days=30)
        subscription.billed_amount = Decimal("200.00")
        subscription.save(
            update_fields=[
                "status",
                "current_period_start",
                "current_period_end",
                "billed_amount",
                "updated_at",
            ]
        )

        summary = run_platform_billing_lifecycle(as_of=timezone.now())

        self.assertEqual(summary["charges_created"], 1)
        self.assertEqual(summary["credits_created"], 1)
        self.assertEqual(summary["waiver_amount"], "200.00")
        self.assertEqual(platform_account_balance(account), Decimal("0.00"))
        self.assertTrue(
            PlatformLedgerEntry.objects.filter(
                school=self.school,
                entry_type=PlatformLedgerEntry.EntryType.CHARGE,
                amount=Decimal("200.00"),
                source="billing_lifecycle",
            ).exists()
        )
        self.assertTrue(
            PlatformLedgerEntry.objects.filter(
                school=self.school,
                entry_type=PlatformLedgerEntry.EntryType.CREDIT,
                amount=Decimal("200.00"),
                source="billing_lifecycle_grant",
            ).exists()
        )

    def test_promotion_redeems_to_cycle_limited_grant(self):
        promotion = BillingPromotion.objects.create(
            code="launch-25",
            name="Launch 25",
            percent_off=Decimal("25.000"),
            country_codes=[],
            is_active=True,
        )

        grant = apply_promotion_to_subscription(
            self.school,
            "launch-25",
            cycle_limit=1,
            reason="Launch campaign",
        )

        promotion.refresh_from_db()
        self.assertEqual(promotion.redemption_count, 1)
        self.assertEqual(grant.grant_type, SubscriptionGrant.GrantType.PROMOTION)
        _account, subscription, _ = ensure_subscription_for_school(self.school)
        terms = preview_subscription_commercial_terms(subscription)
        self.assertEqual(terms["discount_amount"], Decimal("50.00"))
        self.assertEqual(terms["net_amount"], Decimal("150.00"))

    def test_promotion_country_guard(self):
        self.school.country_code = "US"
        self.school.save(update_fields=["country_code", "updated_at"])
        BillingPromotion.objects.create(
            code="ng-only",
            name="Nigeria only",
            percent_off=Decimal("30.000"),
            country_codes=["NG"],
            is_active=True,
        )

        with self.assertRaisesMessage(ValueError, "country"):
            apply_promotion_to_subscription(self.school, "ng-only")


class SubscriptionCatalogSeedCommandTests(TestCase):
    def test_seed_subscription_catalog_is_idempotent(self):
        call_command("seed_subscription_catalog")
        call_command("seed_subscription_catalog")

        self.assertTrue(Plan.objects.filter(slug="free-starter", is_default=True).exists())
        self.assertTrue(Plan.objects.filter(slug="district-ministry").exists())
        self.assertEqual(
            Plan.objects.get(slug="enterprise-network").requires_quote,
            True,
        )
        self.assertTrue(PlanAddon.objects.filter(code="ai-assistant").exists())
        self.assertEqual(
            PlanAddon.objects.get(code="premium-onboarding").billing_unit,
            PlanAddon.BillingUnit.ONE_TIME,
        )
        self.assertTrue(
            BillingPromotion.objects.filter(code="founder-first-year-50").exists()
        )


class CountryBillingProfileSeedTests(TestCase):
    def test_seed_country_billing_profiles_adds_configurable_250_plus_markets(self):
        call_command("seed_country_billing_profiles")

        self.assertGreaterEqual(CountryBillingProfile.objects.count(), 250)
        self.assertTrue(CountryBillingProfile.objects.filter(country_code="XK").exists())
        self.assertTrue(CountryBillingProfile.objects.filter(country_code="ZZ").exists())
        profile = CountryBillingProfile.objects.get(country_code="ZZ")
        self.assertIn("custom_contract", profile.default_billing_cycles)
        self.assertIn("invoice", profile.payment_methods)


class TenantPricingOptionsTests(TestCase):
    def setUp(self):
        CountryMultiplier.objects.update_or_create(
            country_code="US",
            defaults={
                "zone": CountryMultiplier.Zone.A,
                "multiplier": Decimal("1.0000"),
                "tax_rate": Decimal("0.0000"),
                "tax_code": "",
                "name": "United States",
                "is_active": True,
            },
        )
        CountryBillingProfile.objects.update_or_create(
            country_code="US",
            defaults={
                "country_name": "United States",
                "currency_code": "USD",
                "market_tier": CountryBillingProfile.MarketTier.A,
                "price_zone": "A",
                "public_price_mode": CountryBillingProfile.PublicPriceMode.PUBLISHED,
                "default_billing_cycles": ["monthly", "annual"],
                "payment_methods": ["card", "invoice"],
                "tax_behavior": CountryBillingProfile.TaxBehavior.EXCLUSIVE,
                "invoice_locale": "en",
                "promotion_policy": {"annual_discount_percent": 10},
                "is_active": True,
            },
        )
        self.plan = Plan.objects.create(
            name="Tenant Simple",
            slug="tenant-simple",
            base_price=Decimal("100.00"),
            is_active=True,
            tenant_visible=True,
            audience="Growing schools",
            tenant_summary="Simple country-aware plan.",
            billing_cycle_options=["monthly", "annual"],
            payment_method_options=["card", "invoice"],
        )
        PlanAddon.objects.create(
            code="tenant-addon",
            name="Tenant Add-on",
            description="Configurable add-on",
            category="support",
            price=Decimal("10.00"),
            is_active=True,
            tenant_visible=True,
        )
        self.school = School.objects.create(
            name="Tenant Pricing School",
            slug="tenant-pricing-school",
            subdomain="tenant-pricing-school",
            country_code="US",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.REGULAR,
        )
        ensure_subscription_for_school(self.school)

    def test_tenant_pricing_options_are_country_aware_and_simple(self):
        from apps.billing.tenant_pricing import tenant_pricing_options

        options = tenant_pricing_options(self.school)

        self.assertEqual(options["country"]["country_code"], "US")
        self.assertEqual(options["country"]["currency_code"], "USD")
        self.assertIn("invoice", options["country"]["payment_methods"])
        plan = next(row for row in options["plans"] if row["slug"] == "tenant-simple")
        self.assertEqual(plan["monthly_total"], Decimal("100.00"))
        self.assertEqual(plan["annual_total"], Decimal("1080.00"))
        addon = next(row for row in options["addons"] if row["code"] == "tenant-addon")
        self.assertEqual(addon["monthly_total"], Decimal("10.00"))

    def test_missing_country_uses_global_fallback_profile(self):
        CountryBillingProfile.objects.update_or_create(
            country_code="ZZ",
            defaults={
                "country_name": "Global fallback market",
                "currency_code": "USD",
                "default_billing_cycles": ["monthly", "annual", "custom_contract"],
                "payment_methods": ["card", "invoice"],
                "is_active": True,
            },
        )
        # Simulate a TRULY country-less school: clear the explicit country_code AND the
        # region that School.save() auto-derived from it at creation. resolve_school_
        # country_code falls back to default_region otherwise, so without this the school
        # still resolves to US and the ZZ global-fallback profile is never exercised.
        self.school.country_code = ""
        self.school.default_region = None
        self.school.save(
            update_fields=["country_code", "default_region", "updated_at"]
        )
        from apps.billing.tenant_pricing import tenant_pricing_options

        options = tenant_pricing_options(self.school)

        self.assertEqual(options["country"]["country_code"], "ZZ")
