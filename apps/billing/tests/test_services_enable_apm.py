"""Per-domain integration tests for apps.billing.services.enable_apm + set_payment_settings.

The Unified Wizard Framework's fintech writer calls these helpers via
``_try_domain_integration`` so that APM + settlement choices propagate into
``BillingAccount`` first-class metadata on top of the cockpit_payload cascade.
"""

from __future__ import annotations

from django.test import TestCase

from apps.billing import services
from apps.billing.models import BillingAccount
from apps.schools.models import School


class EnableApmTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="APM School",
            slug="apm-school",
            subdomain="apm-school",
            is_active=True,
        )

    def test_enable_apm_creates_billing_account_and_records_key(self):
        self.assertFalse(BillingAccount.objects.filter(school=self.school).exists())

        self.assertTrue(services.enable_apm(self.school, "upi_rupay"))

        account = BillingAccount.objects.get(school=self.school)
        self.assertEqual(account.metadata["enabled_apms"], ["upi_rupay"])

    def test_enable_apm_idempotent(self):
        services.enable_apm(self.school, "mpesa_stk")
        # Second call returns False because already enabled
        self.assertFalse(services.enable_apm(self.school, "mpesa_stk"))
        account = BillingAccount.objects.get(school=self.school)
        self.assertEqual(account.metadata["enabled_apms"], ["mpesa_stk"])

    def test_enable_apm_appends_in_stable_order(self):
        services.enable_apm(self.school, "pix_brcode")
        services.enable_apm(self.school, "upi_rupay")
        services.enable_apm(self.school, "gcash_ph")
        account = BillingAccount.objects.get(school=self.school)
        self.assertEqual(
            account.metadata["enabled_apms"],
            ["pix_brcode", "upi_rupay", "gcash_ph"],
        )

    def test_enable_apm_blank_inputs_noop(self):
        self.assertFalse(services.enable_apm(None, "upi_rupay"))
        self.assertFalse(services.enable_apm(self.school, ""))
        self.assertFalse(services.enable_apm(self.school, "   "))
        self.assertFalse(BillingAccount.objects.filter(school=self.school).exists())


class SetPaymentSettingsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="Settlement School",
            slug="settlement-school",
            subdomain="settlement-school",
            is_active=True,
        )

    def test_currency_lands_on_column(self):
        self.assertTrue(
            services.set_payment_settings(self.school, settlement_currency="INR")
        )
        account = BillingAccount.objects.get(school=self.school)
        self.assertEqual(account.currency_code, "INR")

    def test_country_and_alias_land_in_metadata(self):
        services.set_payment_settings(
            self.school,
            settlement_country="IN",
            settlement_currency="INR",
            settlement_bank_account_alias="primary_inr_account",
        )
        account = BillingAccount.objects.get(school=self.school)
        settlement = account.metadata.get("settlement") or {}
        self.assertEqual(settlement["country"], "IN")
        self.assertEqual(settlement["bank_account_alias"], "primary_inr_account")

    def test_idempotent_when_no_change(self):
        services.set_payment_settings(self.school, settlement_currency="USD")
        self.assertFalse(
            services.set_payment_settings(self.school, settlement_currency="USD")
        )

    def test_invalid_currency_skipped(self):
        services.set_payment_settings(self.school, settlement_currency="USDOLLARS")
        account = BillingAccount.objects.filter(school=self.school).first()
        # Account is created (with default) but bogus currency is not applied
        if account is not None:
            self.assertNotEqual(account.currency_code, "USDOLLARS")

    def test_none_school_returns_false(self):
        self.assertFalse(
            services.set_payment_settings(None, settlement_currency="USD")
        )
