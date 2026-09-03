"""M7 -- payments reliability: the two replay shapes nobody had driven.

The existing soak suites (``test_webhook_duplicate_soak.py``,
``test_webhook_multi_psp_soak.py``) prove exactly-once posting -- but every one
of them replays a PARTIAL payment: 50.00 against a 200.00 invoice, so every
redelivery still has 150.00 of headroom and sails through the amount check on
its way to the dedup claim.

The shape that actually happens in production is the opposite one. A PSP
redelivers the event that settled the invoice IN FULL. On that path the amount
check ran BEFORE the dedup claim, computed ``remaining == 0`` and answered
HTTP 400 "exceeds remaining balance 0". Every PSP treats a 4xx as "the endpoint
is broken, keep retrying" -- so the endpoint rejected, forever, an event it had
already processed perfectly. It also logged the row as INVALID, not FAILED, so
the dead-letter counter in ``views_payments`` (which counts FAILED only) never
tripped to shut the retries down. Nothing was double-charged, but the webhook
was permanently un-ackable.

``test_full_settlement_replay_is_acked_not_rejected`` is the regression seal.
The fix reads the dedup bucket read-only BEFORE any amount arithmetic and acks a
terminal bucket immediately.

The second class covers the partial-failure path: a DB failure part-way through
the money transaction must leave NOTHING behind -- no Payment, no balance
movement -- and must NOT burn the idempotency bucket, or the PSP's retry (the
one thing that would recover the money) would be answered "duplicate" and the
payment would be lost for good.
"""

import hashlib
import hmac
import json
from decimal import Decimal
from unittest import mock

from django.db import DatabaseError
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


class _WebhookFixtureMixin:
    SECRET = "m7-replay-secret"

    def _build_money_graph(self, *, total: Decimal):
        self.profile = ComplianceProfile.objects.create(
            name="M7 Profile",
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
        self.department = Department.objects.create(name="Science", code="M7SCI")
        self.specialty = Specialty.objects.create(
            department=self.department, name="General", code="M7GEN"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 3",
            code="M7F3",
        )
        self.student = StudentProfile.objects.create(
            first_name="Replay",
            last_name="Subject",
            student_code="STD-M7-1",
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
            total_amount=total,
            balance_amount=total,
            issued_date=timezone.now().date(),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=total,
            amount=total,
            fee_item=None,
        )
        Integration.objects.create(
            name="MTN M7",
            slug="mtn-payments-m7",
            provider="payments",
            enabled=True,
            config={"provider_slug": "mtn_momo", "webhook_secret": self.SECRET},
        )

    def _post(self, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(
            self.SECRET.encode(), body, hashlib.sha256
        ).hexdigest()
        return self.client.post(
            reverse("finance:payment_webhook", kwargs={"provider_slug": "mtn_momo"}),
            data=body,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )

    def _paid_total(self) -> Decimal:
        return Payment.objects.filter(invoice=self.invoice).aggregate(
            total=Sum("amount")
        )["total"] or Decimal("0.00")


class FullSettlementReplayTests(_WebhookFixtureMixin, TestCase):
    """A redelivery that leaves ZERO headroom is still just a duplicate."""

    def setUp(self):
        self._build_money_graph(total=Decimal("200.00"))
        self.payload = {
            "provider": "mtn",
            "invoiceId": self.invoice.pk,
            "amount": "200.00",  # settles the invoice IN FULL
            "transaction_id": "m7-settle-tx-1",
            "status": "successful",
        }

    def test_first_delivery_settles_the_invoice(self):
        """Control: the fixture really does reach zero remaining balance.

        Without this the replay assertions below could pass on an invoice that
        was never settled, i.e. against a branch the fixture never fires.
        """
        response = self._post(self.payload)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(self._paid_total(), Decimal("200.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.computed_balance, Decimal("0.00"))

    def test_full_settlement_replay_is_acked_not_rejected(self):
        first = self._post(self.payload)
        self.assertEqual(first.status_code, 200)

        replay = self._post(self.payload)

        # THE SEAL. Before the fix this was 400 "Payment 200.00 exceeds
        # remaining balance 0" -- a permanent 4xx the PSP retries forever.
        self.assertEqual(
            replay.status_code,
            200,
            msg=(
                "settled-invoice replay was rejected instead of acked: "
                f"{replay.status_code} {replay.content[:200]!r}"
            ),
        )
        self.assertEqual(
            replay.json(),
            {"status": "ignored", "reason": "duplicate"},
        )

        # Exactly-once still holds: no second payment, no second charge.
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(self._paid_total(), Decimal("200.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.computed_balance, Decimal("0.00"))

    def test_settled_replay_is_logged_duplicate_not_invalid(self):
        """The log status decides whether the retry storm ever shuts down.

        INVALID is invisible to the dead-letter counter (it counts FAILED), so a
        mislabelled replay retries without limit and without alarm.
        """
        self._post(self.payload)
        self._post(self.payload)

        self.assertEqual(
            WebhookLog.objects.filter(
                provider="mtn_momo", status=WebhookLog.Status.INVALID
            ).count(),
            0,
            msg="a replay of an already-processed event was logged INVALID",
        )
        self.assertEqual(
            WebhookLog.objects.filter(
                provider="mtn_momo", status=WebhookLog.Status.PROCESSED
            ).count(),
            1,
        )
        self.assertEqual(
            WebhookLog.objects.filter(
                provider="mtn_momo", status=WebhookLog.Status.DUPLICATE
            ).count(),
            1,
        )

        # Only the authoritative claim row owns the bucket; audit rows must not,
        # or the next redelivery collides with the partial unique index.
        owners = WebhookLog.objects.filter(provider="mtn_momo").exclude(
            idempotency_bucket=""
        )
        self.assertEqual(owners.count(), 1)
        self.assertEqual(owners.first().status, WebhookLog.Status.PROCESSED)

    def test_five_settled_replays_stay_exactly_once(self):
        for _ in range(5):
            response = self._post(self.payload)
            self.assertEqual(response.status_code, 200)
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(self._paid_total(), Decimal("200.00"))

    def test_a_genuinely_new_overpayment_is_still_refused(self):
        """The fix must not become a hole: a DIFFERENT event that would
        overshoot the invoice is still a 400."""
        self._post(self.payload)
        overshoot = dict(self.payload, transaction_id="m7-settle-tx-2")
        response = self._post(overshoot)
        self.assertEqual(
            response.status_code,
            400,
            msg="a new event overshooting the balance must still be refused",
        )
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(self._paid_total(), Decimal("200.00"))

    def test_a_second_partial_payment_still_posts(self):
        """And a legitimate second instalment on the SAME invoice still lands."""
        partial = dict(self.payload, amount="80.00", transaction_id="m7-part-1")
        self.assertEqual(self._post(partial).status_code, 200)
        second = dict(self.payload, amount="70.00", transaction_id="m7-part-2")
        self.assertEqual(self._post(second).status_code, 200)
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 2)
        self.assertEqual(self._paid_total(), Decimal("150.00"))


class PartialFailureRollbackTests(_WebhookFixtureMixin, TestCase):
    """Money is all-or-nothing, and a failure must leave the bucket reclaimable."""

    def setUp(self):
        self._build_money_graph(total=Decimal("300.00"))
        self.payload = {
            "provider": "mtn",
            "invoiceId": self.invoice.pk,
            "amount": "120.00",
            "transaction_id": "m7-fail-tx-1",
            "status": "successful",
        }

    def test_failure_after_payment_creation_commits_nothing(self):
        """Payment row created, then allocation blows up -> rollback, not a
        half-applied payment sitting against an unmoved invoice balance."""
        with mock.patch(
            "apps.finance.views_payments.record_provider_payment",
            side_effect=DatabaseError("allocation exploded"),
        ) as patched:
            response = self._post(self.payload)

        self.assertTrue(patched.called, msg="the failure was never injected")
        self.assertEqual(response.status_code, 500)
        self.assertEqual(response.json()["reason"], "processing_failed")

        # Nothing committed.
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 0)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.computed_balance, Decimal("300.00"))

        # The failure is recorded, and recorded as FAILED so the dead-letter
        # counter can see it.
        self.assertTrue(
            WebhookLog.objects.filter(
                provider="mtn_momo", status=WebhookLog.Status.FAILED
            ).exists()
        )

    def test_the_psp_retry_after_a_failure_still_posts_the_money(self):
        """The whole point of rolling back: the retry must be able to succeed.

        If the failed attempt kept the idempotency bucket, the retry would be
        answered 'duplicate' and the payment would be lost permanently.
        """
        with mock.patch(
            "apps.finance.views_payments.record_provider_payment",
            side_effect=DatabaseError("transient"),
        ):
            self.assertEqual(self._post(self.payload).status_code, 500)
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 0)

        # PSP retries the identical event.
        retry = self._post(self.payload)
        self.assertEqual(
            retry.status_code,
            200,
            msg=f"retry after a failed attempt was refused: {retry.content[:200]!r}",
        )
        self.assertEqual(retry.json()["status"], "ok")
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 1)
        self.assertEqual(self._paid_total(), Decimal("120.00"))

        # ...and a replay of the now-successful event is still deduped.
        again = self._post(self.payload)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["reason"], "duplicate")
        self.assertEqual(Payment.objects.filter(invoice=self.invoice).count(), 1)
