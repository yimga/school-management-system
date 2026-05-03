"""Settlement ledger honesty + monetization dashboard blocked reasons."""

from __future__ import annotations

from decimal import Decimal

from django.test import RequestFactory, TestCase

from apps.accounts.models import User
from apps.marketplace.models import MarketplaceMonetizationLedgerEntry
from apps.marketplace.monetization_ledger_ops import (
    append_marketplace_ledger_entry,
    append_payment_success_ledger,
)
from apps.marketplace.settlement_truth import (
    PHASE_SETTLEMENT_EXTERNAL_BLOCKED,
    PHASE_SETTLEMENT_PAID,
    settlement_phase_for_event,
)
from apps.marketplace.views_monetization_dashboard import monetization_dashboard
from apps.schools.models import School


class MarketplaceSettlementTruthTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school_a = School.objects.create(
            name="Settle A",
            slug="settle-a",
            subdomain="settla",
            is_active=True,
        )
        cls.school_b = School.objects.create(
            name="Settle B",
            slug="settle-b",
            subdomain="settlb",
            is_active=True,
        )

    def test_settlement_completed_without_proof_raises(self):
        with self.assertRaises(ValueError):
            append_marketplace_ledger_entry(
                school=self.school_a,
                event_type=MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_COMPLETED,
                sku_key="mkt_app_subscription",
                quantity=0,
                amount=Decimal("0.00"),
                idempotency_key="bad-settle-complete:1",
                metadata={},
            )

    def test_settlement_completed_with_reconciliation_audit_ref_allowed(self):
        row = append_marketplace_ledger_entry(
            school=self.school_a,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_COMPLETED,
            sku_key="mkt_app_subscription",
            quantity=0,
            amount=Decimal("0.00"),
            idempotency_key="good-settle-complete:manual:1",
            metadata={"reconciliation_audit_ref": "audit-ledger-42"},
        )
        self.assertIsNotNone(row.pk)

    def test_payment_success_production_writes_confirmation_ref_on_completed_path(self):
        append_payment_success_ledger(
            school=self.school_a,
            app=None,
            amount=Decimal("12.00"),
            currency="USD",
            processor_ref="evt_live_confirm_001",
            processor_code="stripe",
            production_psp=True,
        )
        settle = MarketplaceMonetizationLedgerEntry.objects.filter(
            school=self.school_a,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_COMPLETED,
        ).first()
        self.assertIsNotNone(settle)
        md = settle.metadata if isinstance(settle.metadata, dict) else {}
        self.assertEqual(
            md.get("provider_settlement_confirmation_ref"),
            "evt_live_confirm_001",
        )

    def test_phase_mapping_external_blocked_and_paid(self):
        self.assertEqual(
            settlement_phase_for_event(
                MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_EXTERNAL_BLOCKED
            ),
            PHASE_SETTLEMENT_EXTERNAL_BLOCKED,
        )
        self.assertEqual(
            settlement_phase_for_event(
                MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_COMPLETED
            ),
            PHASE_SETTLEMENT_PAID,
        )

    def test_dashboard_surfaces_blocked_reason_staff(self):
        append_marketplace_ledger_entry(
            school=self.school_a,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_EXTERNAL_BLOCKED,
            sku_key="mkt_app_subscription",
            quantity=0,
            amount=Decimal("0.00"),
            idempotency_key="blocked-detail-a",
            metadata={
                "reason": "payment_readiness_missing_setup",
                "readiness_tier": "MISSING_SETUP",
            },
        )
        append_marketplace_ledger_entry(
            school=self.school_b,
            event_type=MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_EXTERNAL_BLOCKED,
            sku_key="mkt_app_subscription",
            quantity=0,
            amount=Decimal("0.00"),
            idempotency_key="blocked-detail-b-only",
            metadata={"reason": "UNIQUE_BLOCKER_B_ONLY"},
        )
        user = User.objects.create_user(
            username="settle_staff",
            password="Pass_12345",
            is_staff=True,
        )
        factory = RequestFactory()
        request = factory.get("/tenant/marketplace/monetization/")
        request.user = user
        request.school = self.school_a
        response = monetization_dashboard(request)
        self.assertEqual(response.status_code, 200)
        body = response.content.decode("utf-8")
        self.assertIn("payment_readiness_missing_setup", body)
        self.assertIn("MISSING_SETUP", body)
        self.assertNotIn("UNIQUE_BLOCKER_B_ONLY", body)
