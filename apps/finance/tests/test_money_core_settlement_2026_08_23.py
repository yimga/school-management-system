"""Money-core settlement contract: online payments SETTLE, and every
paid-total gate nets refunds/failures the same way.

Three holes closed here, all on the parent-pays-fees path:

1. ``record_provider_payment`` (the gateway webhook's sole Payment producer)
   and ``pay_invoice_with_wallet`` never set ``Payment.status``, so every
   M-Pesa / MTN MoMo / Paystack / wallet receipt stayed ``pending`` forever.
   Nothing downstream promotes it (``mark_completed`` has no production
   caller), so the payment-received notification never fired, the processor
   revenue-share accrual never ran, and the OHADA statutory revenue report
   (which filters ``status="completed"``) omitted every online receipt.

2. ``Payment.clean()`` computed the already-paid total from GROSS payment
   amounts -- it excluded soft-deleted rows but not failed/cancelled/refunded
   ones, and never netted ``refunded_amount`` -- despite its comment claiming
   parity with ``Invoice.computed_balance``. A partially refunded invoice
   could therefore never be re-collected: the bursar's new payment was
   rejected as "exceeds remaining balance 0" while the invoice itself showed
   money owing.

3. The payment webhook validated the callback amount against that same gross
   sum (``sum(invoice.payments.values_list("amount"))``), so a legitimate
   signed PSP callback on an invoice with any reversed history 400'd -- and
   after the dead-letter threshold the endpoint started acking 200 and
   dropping the payment entirely.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    ParentWallet,
    Payment,
    PaymentMethodCode,
    RefundRequest,
    WebhookLog,
)
from apps.finance.services import (
    pay_invoice_with_wallet,
    process_refund_request,
    record_provider_payment,
)
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import Integration, RegionConfig

User = get_user_model()


class _MoneyCoreBase(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Settlement School",
            slug="settle-mc",
            subdomain="settle-mc",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name="Settlement", country_code="CM", currency_code="XAF"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026-settle",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ama",
            last_name="Nkemi",
            student_code="STU-MC-1",
            academic_year=self.year,
            is_active=True,
        )
        self.invoice = self._invoice("INV-MC-001", "1000.00")

    def _invoice(self, reference, total):
        invoice = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            student=self.student,
            academic_year=self.year,
            reference=reference,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate(),
            total_amount=Decimal(total),
            balance_amount=Decimal(total),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal(total),
            amount=Decimal(total),
        )
        return invoice


class OnlinePaymentsSettleTests(_MoneyCoreBase):
    def test_gateway_payment_is_recorded_as_completed(self):
        payment = record_provider_payment(
            invoice=self.invoice,
            amount="600.00",
            method=PaymentMethodCode.MTN_MOMO,
            reference="MOMO-REF-600",
            external_reference="MOMO-TXN-600",
        )
        # Reached the producer at all (a None return would make every
        # assertion below vacuous).
        self.assertIsNotNone(payment)
        self.assertIsNotNone(payment.pk)
        payment.refresh_from_db()

        self.assertEqual(payment.amount, Decimal("600.00"))
        self.assertEqual(
            payment.status,
            "completed",
            "a PSP callback that reaches record_provider_payment is settled money",
        )
        # _guardian_contacts_for_payment / _resolve_school read these off the
        # Payment row, not the invoice.
        self.assertEqual(payment.school_id, self.school.pk)
        self.assertEqual(payment.student_id, self.student.pk)

    def test_gateway_payment_fires_the_payment_received_notification(self):
        # The end consequence of the pending-forever bug: apply_payment's
        # notification gate requires status in (completed/success/paid), so a
        # guardian got NO payment-received message for any online payment.
        with patch(
            "apps.finance.payment_notification_intent.dispatch_payment_received_intent"
        ) as dispatch:
            payment = record_provider_payment(
                invoice=self.invoice,
                amount="250.00",
                method=PaymentMethodCode.MTN_MOMO,
                reference="MOMO-REF-250",
                external_reference="MOMO-TXN-250",
            )
        self.assertIsNotNone(payment)
        self.assertTrue(
            dispatch.called,
            "guardian must be notified that their gateway payment landed",
        )
        self.assertEqual(dispatch.call_args.kwargs["payment"].pk, payment.pk)

    def test_wallet_payment_is_recorded_as_completed(self):
        parent = User.objects.create_user(
            username="mc_parent",
            email="mc_parent@example.com",
            password="pw",
            role=User.Role.PARENT,
        )
        ParentWallet.objects.create(
            school=self.school,
            user=parent,
            balance=Decimal("1000.00"),
            currency_code="XAF",
        )
        payment, _wallet = pay_invoice_with_wallet(
            school=self.school,
            user=parent,
            invoice=self.invoice,
            amount=Decimal("400.00"),
        )
        self.assertIsNotNone(payment.pk)
        payment.refresh_from_db()
        self.assertEqual(payment.amount, Decimal("400.00"))
        self.assertEqual(payment.status, "completed")
        self.assertEqual(payment.school_id, self.school.pk)
        self.assertEqual(payment.student_id, self.student.pk)


class PaymentCleanNetsRefundsAndFailuresTests(_MoneyCoreBase):
    def setUp(self):
        super().setUp()
        self.region, _ = RegionConfig.objects.get_or_create(
            code="MCT",
            defaults={
                "name": "Money Core Test",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.staff = User.objects.create_user("mc-bursar", "mcb@test.com", "pass")

    def test_partially_refunded_invoice_can_be_re_collected(self):
        original = Payment.objects.create(
            invoice=self.invoice,
            school=self.school,
            amount=Decimal("1000.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
        )
        refund = RefundRequest.objects.create(
            payment=original,
            region=self.region,
            amount=Decimal("400.00"),
            reason="overpayment",
            description="partial refund",
            status="pending",
            requested_by=self.staff,
        )
        process_refund_request(refund, processed_by=self.staff)

        self.invoice.refresh_from_db()
        # Vacuity guard: the parent really does owe 400 again, so the new
        # payment below is a legitimate collection and not an overpayment.
        self.assertEqual(self.invoice.computed_balance, Decimal("400.00"))

        replacement = Payment.objects.create(
            invoice=self.invoice,
            school=self.school,
            amount=Decimal("400.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
        )
        self.assertIsNotNone(replacement.pk)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.computed_balance, Decimal("0.00"))

    def test_failed_payment_does_not_block_a_retry(self):
        first = Payment.objects.create(
            invoice=self.invoice,
            school=self.school,
            amount=Decimal("1000.00"),
            method=PaymentMethodCode.CASH,
            status="pending",
        )
        first.mark_failed(reason="insufficient funds")
        first.refresh_from_db()
        # Vacuity guard: mark_failed does NOT soft-delete, so the row is still
        # visible to the deleted_at-only filter that Payment.clean() used.
        self.assertEqual(first.status, "failed")
        self.assertIsNone(first.deleted_at)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.computed_balance, Decimal("1000.00"))

        retry = Payment.objects.create(
            invoice=self.invoice,
            school=self.school,
            amount=Decimal("1000.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
        )
        self.assertIsNotNone(retry.pk)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.computed_balance, Decimal("0.00"))

    def test_clean_still_rejects_a_genuine_overpayment(self):
        # The fix must not open the gate entirely.
        Payment.objects.create(
            invoice=self.invoice,
            school=self.school,
            amount=Decimal("600.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
        )
        with self.assertRaises(ValidationError):
            Payment.objects.create(
                invoice=self.invoice,
                school=self.school,
                amount=Decimal("500.00"),
                method=PaymentMethodCode.CASH,
                status="completed",
            )


class WebhookAmountGateUsesNetPaidTests(_MoneyCoreBase):
    """A signed PSP callback on an invoice with reversed history must post."""

    SLUG = "money-core-psp"
    SECRET = "money-core-webhook-secret"

    def setUp(self):
        super().setUp()
        Integration.objects.create(
            name="Money Core PSP",
            slug=self.SLUG,
            provider="payments",
            enabled=True,
            config={"webhook_secret": self.SECRET},
        )

    def _post(self, payload: dict):
        raw = json.dumps(payload).encode("utf-8")
        signature = hmac.new(
            self.SECRET.encode("ascii"), raw, hashlib.sha256
        ).hexdigest()
        return self.client.post(
            reverse("finance:payment_webhook", kwargs={"provider_slug": self.SLUG}),
            data=raw,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )

    def test_callback_posts_after_a_failed_prior_attempt(self):
        failed = Payment.objects.create(
            invoice=self.invoice,
            school=self.school,
            amount=Decimal("1000.00"),
            method=PaymentMethodCode.MTN_MOMO,
            status="pending",
        )
        failed.mark_failed(reason="momo timeout")
        self.invoice.refresh_from_db()
        # Vacuity guard: the invoice is genuinely unpaid, so a 1000 callback is
        # a valid settlement -- any rejection is the gross-sum bug, not fraud.
        self.assertEqual(self.invoice.computed_balance, Decimal("1000.00"))

        response = self._post(
            {
                "invoice_id": self.invoice.pk,
                "amount": "1000.00",
                "reference": "MOMO-RETRY-1",
                "status": "success",
                "method": "MTN",
            }
        )

        self.assertEqual(
            response.status_code,
            200,
            f"webhook rejected a legitimate settlement: {response.content!r}",
        )
        body = json.loads(response.content)
        self.assertEqual(body.get("status"), "ok", body)
        # The request really reached record_provider_payment.
        settled = Payment.objects.filter(
            invoice=self.invoice, external_reference="MOMO-RETRY-1"
        ).first()
        self.assertIsNotNone(settled, "no Payment row was created for the callback")
        self.assertEqual(settled.amount, Decimal("1000.00"))
        self.assertEqual(settled.status, "completed")
        self.assertFalse(
            WebhookLog.objects.filter(status=WebhookLog.Status.INVALID).exists(),
            "a valid signed callback must not be logged INVALID",
        )
