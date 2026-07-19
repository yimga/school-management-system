"""Duplicate / replay webhook soak — exactly-once posting on the money path.

Covers the two paths the older contract tests did NOT drive end-to-end:

1. The provider-event-id dedup bucket path (``compute_idempotency_bucket`` ->
   per-provider ``_EXTRACTORS``) — a PSP redelivering the IDENTICAL event with
   the same ``transaction_id`` and NO client Idempotency-Key header. This is the
   most common real-world replay shape. Asserts exactly ONE Payment posts, the
   invoice balance is charged exactly once, and duplicate/replay deliveries are
   acked 200 "ignored" (not a 500 retry storm).

2. A rejected first delivery (bad signature) must NOT poison the bucket and
   block the real payment's later valid delivery — audit rows never own the
   idempotency bucket, only the authoritative claim row does.

Regression seal for the finance_webhooklog_uniq_provider_bucket collision that
made every duplicate redelivery 500 (see views_payments.py::_create_webhook_log).
"""

import hashlib
import hmac
import json
from decimal import Decimal

from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    WebhookLog,
)
from apps.people.models import StudentProfile
from apps.siteconfig.models import Integration


class WebhookDuplicateSoakTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon Soak",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="XAF",
            timezone="Africa/Douala",
            chart_template=ComplianceProfile.ChartTemplate.OHADA,
            min_wage=Decimal("60000"),
            default_hours_per_week=Decimal("40"),
            overtime_multiplier=Decimal("1.5"),
            annual_leave_days=21,
            maternity_leave_days=84,
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.department = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(
            department=self.department, name="General", code="GEN"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 2",
            code="F2",
        )
        self.student = StudentProfile.objects.create(
            first_name="Soak",
            last_name="Student",
            student_code="STD-SOAK-1",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("200.00"),
            balance_amount=Decimal("200.00"),
            issued_date=timezone.now().date(),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal("200.00"),
            amount=Decimal("200.00"),
            fee_item=None,
        )
        self.secret = "mtn-soak-secret"
        Integration.objects.create(
            name="MTN Soak",
            slug="mtn-payments-soak",
            provider="payments",
            enabled=True,
            config={"provider_slug": "mtn_momo", "webhook_secret": self.secret},
        )

    def _post(self, payload: dict, *, signature_override: str | None = None):
        body = json.dumps(payload).encode("utf-8")
        signature = (
            signature_override
            if signature_override is not None
            else hmac.new(self.secret.encode(), body, hashlib.sha256).hexdigest()
        )
        return self.client.post(
            reverse("finance:payment_webhook", kwargs={"provider_slug": "mtn_momo"}),
            data=body,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )

    def test_provider_event_id_replay_posts_exactly_once(self):
        """Same transaction_id, no Idempotency-Key, delivered 3x -> one payment."""
        payload = {
            "provider": "mtn",
            "invoiceId": self.invoice.pk,
            "amount": "50.00",
            "transaction_id": "mtn-soak-tx-1",
            "status": "successful",
        }
        bucket = "mtn_momo:mtn-soak-tx-1"

        first = self._post(payload)
        # Original + duplicate + a later replay (after full processing).
        second = self._post(payload)
        third = self._post(payload)

        self.assertEqual(first.status_code, 200)
        self.assertEqual(first.json().get("status"), "ok")
        for later in (second, third):
            self.assertEqual(later.status_code, 200)
            self.assertEqual(later.json().get("status"), "ignored")
            self.assertEqual(later.json().get("reason"), "duplicate")

        # Exactly one payment; ledger/balance charged exactly once.
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(
            Payment.objects.filter(external_reference="mtn-soak-tx-1").count(), 1
        )
        total_posted = Payment.objects.filter(invoice=self.invoice).aggregate(
            total=Sum("amount")
        )["total"]
        self.assertEqual(total_posted, Decimal("50.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_amount, Decimal("150.00"))

        # The authoritative claim row owns the bucket; it is the only PROCESSED row.
        processed = WebhookLog.objects.filter(
            provider="mtn_momo", status=WebhookLog.Status.PROCESSED
        )
        self.assertEqual(processed.count(), 1)
        self.assertEqual(processed.get().idempotency_bucket, bucket)

        # Two duplicate deliveries -> two DUPLICATE audit rows, none owning the
        # bucket (that would collide with the unique constraint and 500).
        duplicates = WebhookLog.objects.filter(
            provider="mtn_momo", status=WebhookLog.Status.DUPLICATE
        )
        self.assertEqual(duplicates.count(), 2)
        for dup in duplicates:
            self.assertEqual(dup.idempotency_bucket, "")
            self.assertTrue(dup.signature_valid)
            self.assertEqual(dup.response_status, 200)

    def test_rejected_first_delivery_does_not_block_later_valid_payment(self):
        """A bad-signature first delivery must not poison the bucket.

        Before the audit-row bucket fix, the rejected INVALID row owned
        (provider, bucket); the real payment's later claim then resolved as a
        false 'duplicate' and never posted (silent payment loss / poison DoS).
        """
        payload = {
            "provider": "mtn",
            "invoiceId": self.invoice.pk,
            "amount": "50.00",
            "transaction_id": "mtn-soak-tx-2",
            "status": "successful",
        }

        rejected = self._post(payload, signature_override="deadbeef")
        self.assertEqual(rejected.status_code, 403)
        self.assertFalse(
            Payment.objects.filter(external_reference="mtn-soak-tx-2").exists()
        )

        accepted = self._post(payload)
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.json().get("status"), "ok")
        self.assertEqual(
            Payment.objects.filter(external_reference="mtn-soak-tx-2").count(), 1
        )
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.balance_amount, Decimal("150.00"))
