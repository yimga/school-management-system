"""Uniform marketplace monetization ledger — idempotency, isolation, honest settlement flags."""

from __future__ import annotations

from decimal import Decimal

from django.test import TestCase

from apps.billing.services import finalize_marketplace_addon_payment
from apps.marketplace.models import (
    MarketplaceApp,
    MarketplaceListing,
    MarketplaceMonetizationLedgerEntry,
    PublisherOrganization,
)
from apps.marketplace.monetization import record_usage_meter_increment
from apps.marketplace.monetization_ledger_ops import (
    append_marketplace_ledger_entry,
    append_payment_success_ledger,
    classify_settlement_lane,
    infer_production_psp_for_ledger,
)
from apps.schools.models import School


class MarketplaceLedgerTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Ledger A",
            slug="ledger-a",
            subdomain="ledger-a",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="Ledger B",
            slug="ledger-b",
            subdomain="ledger-b",
            is_active=True,
        )
        cls.publisher = PublisherOrganization.objects.create(
            slug="led-pub",
            name="Led Pub",
        )
        cls.app = MarketplaceApp.objects.create(
            slug="led-app",
            app_key="led-app",
            name="Led App",
            version="1.0.0",
            publisher=cls.publisher,
            pricing_model=MarketplaceApp.PricingModel.SUBSCRIPTION,
            price=Decimal("10.00"),
            billing_interval=MarketplaceApp.BillingInterval.MONTHLY,
        )
        MarketplaceListing.objects.create(
            app=cls.app,
            publisher=cls.publisher,
            status=MarketplaceListing.Status.APPROVED,
            revenue_share_percent=Decimal("50.00"),
            short_description="x",
        )

    def test_idempotent_replay_returns_same_row(self):
        row1 = append_marketplace_ledger_entry(
            school=self.school_a,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.USAGE_RECORDED,
            sku_key="platform_ai_usage",
            quantity=3,
            amount=Decimal("0.00"),
            idempotency_key="idem:usage:1",
        )
        row2 = append_marketplace_ledger_entry(
            school=self.school_a,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.USAGE_RECORDED,
            sku_key="platform_ai_usage",
            quantity=99,
            amount=Decimal("0.00"),
            idempotency_key="idem:usage:1",
        )
        self.assertEqual(row1.pk, row2.pk)

    def test_tenant_cannot_see_other_school_ledger(self):
        append_marketplace_ledger_entry(
            school=self.school_a,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.INSTALL,
            sku_key="mkt_app_subscription",
            quantity=1,
            amount=Decimal("1.00"),
            idempotency_key="idem:cross:a",
        )
        qs_b = MarketplaceMonetizationLedgerEntry.objects.filter(school=self.school_b)
        self.assertEqual(qs_b.count(), 0)

    def test_classify_test_context_never_production_psp(self):
        lane = classify_settlement_lane(self.school_a)
        self.assertEqual(lane.get("lane"), "test_mode")
        self.assertFalse(lane.get("production_psp"))

    def test_infer_production_psp_relay_processor_false(self):
        prod = infer_production_psp_for_ledger(
            self.school_a,
            {"event_type": "checkout.session.completed"},
            "relay",
        )
        self.assertFalse(prod)

    def test_usage_meter_increment_with_ledger_idempotency(self):
        record_usage_meter_increment(
            school=self.school_a,
            metric_code="ai_usage_units",
            quantity=2,
            ledger_sku_key="platform_ai_usage",
            ledger_idempotency_key="meter-proof:1",
        )
        record_usage_meter_increment(
            school=self.school_a,
            metric_code="ai_usage_units",
            quantity=2,
            ledger_sku_key="platform_ai_usage",
            ledger_idempotency_key="meter-proof:1",
        )
        self.assertEqual(
            MarketplaceMonetizationLedgerEntry.objects.filter(
                school=self.school_a,
                idempotency_key="meter-proof:1",
            ).count(),
            1,
        )

    def test_payment_success_ledger_never_completed_for_non_live_processor(self):
        append_payment_success_ledger(
            school=self.school_a,
            app=self.app,
            amount=Decimal("40.00"),
            currency="USD",
            processor_ref="cs_test_sess_proof",
            processor_code="relay",
            production_psp=False,
        )
        completed = MarketplaceMonetizationLedgerEntry.objects.filter(
            school=self.school_a,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_COMPLETED,
        ).exists()
        self.assertFalse(completed)
        pending = MarketplaceMonetizationLedgerEntry.objects.filter(
            school=self.school_a,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_PENDING_EXTERNAL,
        ).exists()
        self.assertTrue(pending)

    def test_finalize_marketplace_addon_writes_ledger_when_not_skipped(self):
        """Relay snapshot must not claim production PSP settlement."""
        snap = {
            "event_type": "checkout.session.completed",
            "marketplace_app_id": str(self.app.pk),
            "processor_source_ref": "cs_test_sess_finalize",
            "billed_amount": "40.00",
            "currency_code": "USD",
        }
        finalize_marketplace_addon_payment(
            self.school_a,
            snap,
            processor_code="relay",
        )
        pay = MarketplaceMonetizationLedgerEntry.objects.filter(
            school=self.school_a,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.PAYMENT_SUCCESS,
            provider_reference="cs_test_sess_finalize",
        ).first()
        self.assertIsNotNone(pay)
        md = pay.metadata if isinstance(pay.metadata, dict) else {}
        self.assertFalse(md.get("production_psp", True))
