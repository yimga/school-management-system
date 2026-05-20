"""Platform billing webhook ledger idempotency — duplicate events must not double-charge."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.billing.models import PlatformLedgerEntry
from apps.billing.services import apply_processor_snapshot, ensure_subscription_for_school
from apps.schools.models import School
from apps.siteconfig.models import Plan


class BillingLedgerIdempotencyTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Idempotency Plan",
            slug="idempotency-plan",
            base_price=Decimal("199.00"),
            is_active=True,
        )
        self.school = School.objects.create(
            name="Idempotency Billing School",
            slug="idempotency-billing-school",
            subdomain="idempotency-billing-school",
            is_active=True,
            plan=self.plan,
            billing_type=School.BillingType.REGULAR,
        )
        ensure_subscription_for_school(self.school)

    def test_duplicate_paid_snapshot_creates_single_ledger_entry(self):
        src_ref = "pi_idempotency_stage5_001"
        snapshot_kwargs = dict(
            school=self.school,
            processor_code="relay",
            event_type="invoice.paid",
            account_status="active",
            subscription_status="active",
            billed_amount=Decimal("199.00"),
            processor_source_ref=src_ref,
            happened_at=timezone.now(),
        )
        apply_processor_snapshot(**snapshot_kwargs)
        apply_processor_snapshot(**snapshot_kwargs)

        ref = f"relay:invoice.paid:{src_ref}"
        entries = PlatformLedgerEntry.objects.filter(
            reference=ref, source="stripe_webhook"
        )
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.get().amount, Decimal("199.00"))

    def test_checkout_completed_snapshot_dedupes_by_reference(self):
        src_ref = "cs_idempotency_stage5_002"
        ref = f"relay:checkout.session.completed:{src_ref}"
        kwargs = dict(
            school=self.school,
            processor_code="relay",
            event_type="checkout.session.completed",
            billed_amount=Decimal("50.00"),
            processor_source_ref=src_ref,
            account_status="active",
            subscription_status="active",
        )
        apply_processor_snapshot(**kwargs)
        apply_processor_snapshot(**kwargs)
        entries = PlatformLedgerEntry.objects.filter(
            reference=ref, source="stripe_webhook"
        )
        self.assertEqual(entries.count(), 1)
        self.assertEqual(entries.get().amount, Decimal("50.00"))
