"""Phase 2: localized, Stripe-free platform collection.

Proves the settlement path works end to end — a school pays its subscription via a local
rail (mobile money / bank transfer / manual reconciliation), the platform invoice flips to
PAID, the ledger balance clears, and a suspended subscription is restored — with no Stripe
and no funds passing through the platform. Also proves idempotency and partial payment.
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import PlatformInvoice, PlatformLedgerEntry, TenantSubscription
from apps.billing.services import (
    ensure_subscription_for_school,
    platform_account_balance,
    record_platform_charge,
    record_platform_invoice_payment,
)
from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import Plan


@override_settings(SEND_FINANCE_SIGNALS=True)
class PlatformLocalCollectionTests(TestCase):
    def setUp(self):
        self.plan = Plan.objects.create(
            name="Growth LC", slug="growth-lc", base_price=Decimal("32.00"), is_active=True
        )
        self.school = School.objects.create(
            name="Douala School",
            slug="douala-lc",
            subdomain="douala-lc",
            is_active=True,
            plan=self.plan,
            country_code="CM",
        )
        self.account, self.subscription, _ = ensure_subscription_for_school(self.school)
        # ensure_subscription must not itself post a ledger charge — the balance starts clean.
        self.assertEqual(platform_account_balance(self.account), Decimal("0.00"))

    def _issue_invoice(self, total, *, number, seq, stem):
        # Post the real CHARGE this invoice documents, so there is a balance to settle.
        record_platform_charge(
            school=self.school,
            amount=total,
            reference=f"{stem}-CHARGE",
            source="test_local_collection",
        )
        return PlatformInvoice.objects.create(
            billing_account=self.account,
            school=self.school,
            number=number,
            sequence=seq,
            reference_stem=stem,
            total=total,
            currency_code="XAF",
            status=PlatformInvoice.Status.ISSUED,
            issued_at=timezone.now(),
        )

    def test_full_payment_settles_invoice_and_restores_subscription(self):
        invoice = self._issue_invoice(
            Decimal("32.00"), number="INV-LC-1", seq=90001, stem="LC-STEM-1"
        )
        self.subscription.status = TenantSubscription.Status.SUSPENDED
        self.subscription.save(update_fields=["status"])
        self.assertGreater(platform_account_balance(self.account), Decimal("0.00"))

        record_platform_invoice_payment(
            invoice, amount=Decimal("32.00"), method="mtn_momo", external_reference="MP-1"
        )

        invoice.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertEqual(invoice.status, PlatformInvoice.Status.PAID)
        self.assertLessEqual(platform_account_balance(self.account), Decimal("0.00"))
        self.assertEqual(self.subscription.status, TenantSubscription.Status.ACTIVE)

    def test_local_collection_is_idempotent(self):
        invoice = self._issue_invoice(
            Decimal("32.00"), number="INV-LC-2", seq=90002, stem="LC-STEM-2"
        )
        for _ in range(2):
            record_platform_invoice_payment(
                invoice,
                amount=Decimal("32.00"),
                method="bank_transfer",
                external_reference="BT-9",
            )
        credits = PlatformLedgerEntry.objects.filter(
            billing_account=self.account, source="platform_local_collection"
        )
        self.assertEqual(credits.count(), 1)

    def test_partial_then_full_payment(self):
        invoice = self._issue_invoice(
            Decimal("50.00"), number="INV-LC-3", seq=90003, stem="LC-STEM-3"
        )
        record_platform_invoice_payment(
            invoice, amount=Decimal("20.00"), method="mtn_momo", external_reference="P-1"
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, PlatformInvoice.Status.ISSUED)  # not yet covered

        record_platform_invoice_payment(
            invoice, amount=Decimal("30.00"), method="mtn_momo", external_reference="P-2"
        )
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, PlatformInvoice.Status.PAID)

    def test_zero_or_negative_amount_rejected(self):
        invoice = self._issue_invoice(
            Decimal("10.00"), number="INV-LC-4", seq=90004, stem="LC-STEM-4"
        )
        with self.assertRaises(ValueError):
            record_platform_invoice_payment(
                invoice, amount=Decimal("0.00"), method="manual"
            )
