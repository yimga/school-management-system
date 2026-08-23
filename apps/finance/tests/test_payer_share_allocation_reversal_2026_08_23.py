"""Split-billing payer shares must un-allocate when the money goes away.

``allocate_payment_to_payer_shares`` was one-way: every Payment post_save
created ``InvoicePayerSharePaymentAllocation`` rows and incremented
``share.paid_amount`` with NO status check, and nothing in the repo ever
deleted an allocation or decremented a share again.

So on a 1000 invoice split 500/500 between two guardians: guardian A pays 500,
their share flips to PAID -- then the payment is refunded (or fails, or is
reversed). ``recalculate_invoice`` correctly puts the invoice balance back to
1000, but share A still reads paid_amount=500 / status=PAID.
``run_split_late_fees`` excludes ``status=PAID`` and skips shares whose
``outstanding_amount <= 0``, so guardian A accrued no late fee and appeared
settled on the invoice detail page while the invoice showed 1000 outstanding.
Guardian A was never chased for money they no longer had paid.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    InvoicePayerShare,
    InvoicePayerSharePaymentAllocation,
    Payment,
    PaymentMethodCode,
    RefundRequest,
)
from apps.finance.services import (
    assign_invoice_payer_shares,
    process_refund_request,
)
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School
from apps.siteconfig.models import RegionConfig

User = get_user_model()


class PayerShareAllocationReversalTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Split School",
            slug="split-mc",
            subdomain="split-mc",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name="Split", country_code="CM", currency_code="XAF"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026-split",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Njoya",
            last_name="Tabi",
            student_code="STU-SPLIT-1",
            academic_year=self.year,
            is_active=True,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            student=self.student,
            academic_year=self.year,
            reference="INV-SPLIT-001",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate(),
            total_amount=Decimal("1000.00"),
            balance_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal("1000.00"),
            amount=Decimal("1000.00"),
        )
        self.guardian_a = self._guardian("split_parent_a")
        self.guardian_b = self._guardian("split_parent_b")
        self.share_a, self.share_b = self._assign_even_split()

        self.region, _ = RegionConfig.objects.get_or_create(
            code="SPL",
            defaults={
                "name": "Split Test",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.staff = User.objects.create_user("split-bursar", "sb@test.com", "pass")

    def _guardian(self, username):
        user = User.objects.create_user(
            username=username,
            email=f"{username}@example.com",
            password="pw",
            role=User.Role.PARENT,
        )
        return StudentGuardian.objects.create(
            guardian_user=user, student=self.student
        )

    def _assign_even_split(self):
        assign_invoice_payer_shares(
            self.invoice,
            [
                (self.guardian_a, Decimal("500.00")),
                (self.guardian_b, Decimal("500.00")),
            ],
            due_date=self.invoice.due_date,
        )
        shares = list(
            InvoicePayerShare.objects.filter(invoice=self.invoice).order_by("id")
        )
        self.assertEqual(len(shares), 2)
        return shares

    def _pay(self, amount="500.00"):
        payment = Payment.objects.create(
            invoice=self.invoice,
            school=self.school,
            student=self.student,
            amount=Decimal(amount),
            method=PaymentMethodCode.CASH,
            status="completed",
        )
        # Vacuity guard: the allocation producer really ran. Without this a
        # broken producer would make every "un-allocated" assertion below pass
        # for the wrong reason.
        self.assertEqual(
            InvoicePayerSharePaymentAllocation.objects.filter(
                payment=payment
            ).count(),
            1,
        )
        paid_share = InvoicePayerShare.objects.get(
            pk=self._allocated_share_pk(payment)
        )
        self.assertEqual(paid_share.paid_amount, Decimal(amount))
        return payment, paid_share

    @staticmethod
    def _allocated_share_pk(payment):
        return (
            InvoicePayerSharePaymentAllocation.objects.filter(payment=payment)
            .values_list("payer_share_id", flat=True)
            .first()
        )

    def test_full_refund_un_allocates_the_payer_share(self):
        payment, paid_share = self._pay("500.00")
        self.assertEqual(paid_share.status, InvoicePayerShare.Status.PAID)

        refund = RefundRequest.objects.create(
            payment=payment,
            region=self.region,
            amount=Decimal("500.00"),
            reason="duplicate",
            description="full refund",
            status="pending",
            requested_by=self.staff,
        )
        process_refund_request(refund, processed_by=self.staff)

        # The invoice balance already came back correctly before this fix --
        # the share is what stayed stale.
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.computed_balance, Decimal("1000.00"))

        paid_share.refresh_from_db()
        self.assertEqual(paid_share.paid_amount, Decimal("0.00"))
        self.assertNotEqual(
            paid_share.status,
            InvoicePayerShare.Status.PAID,
            "a refunded guardian must be chased again, not left marked PAID",
        )
        self.assertEqual(paid_share.outstanding_amount, Decimal("500.00"))
        self.assertFalse(
            InvoicePayerSharePaymentAllocation.objects.filter(
                payment=payment
            ).exists(),
            "the allocation row must be released, not orphaned",
        )

    def test_partial_refund_reduces_the_payer_share_to_its_net(self):
        payment, paid_share = self._pay("500.00")

        refund = RefundRequest.objects.create(
            payment=payment,
            region=self.region,
            amount=Decimal("200.00"),
            reason="incorrect_amount",
            description="partial refund",
            status="pending",
            requested_by=self.staff,
        )
        process_refund_request(refund, processed_by=self.staff)

        paid_share.refresh_from_db()
        self.assertEqual(paid_share.paid_amount, Decimal("300.00"))
        self.assertEqual(paid_share.status, InvoicePayerShare.Status.PARTIAL)
        self.assertEqual(paid_share.outstanding_amount, Decimal("200.00"))

    def test_marking_a_payment_failed_un_allocates_the_payer_share(self):
        payment, paid_share = self._pay("500.00")

        payment.mark_failed(reason="cheque bounced")

        paid_share.refresh_from_db()
        self.assertEqual(paid_share.paid_amount, Decimal("0.00"))
        self.assertNotEqual(paid_share.status, InvoicePayerShare.Status.PAID)
        self.assertFalse(
            InvoicePayerSharePaymentAllocation.objects.filter(
                payment=payment
            ).exists()
        )

    def test_soft_deleting_a_payment_un_allocates_the_payer_share(self):
        payment, paid_share = self._pay("500.00")

        payment.delete()

        paid_share.refresh_from_db()
        self.assertEqual(paid_share.paid_amount, Decimal("0.00"))
        self.assertNotEqual(paid_share.status, InvoicePayerShare.Status.PAID)

    def test_a_failed_payment_never_allocates_in_the_first_place(self):
        payment = Payment.objects.create(
            invoice=self.invoice,
            school=self.school,
            student=self.student,
            amount=Decimal("500.00"),
            method=PaymentMethodCode.CASH,
            status="failed",
        )
        # Vacuity guard: the row exists and the producer was reached (post_save
        # fires for every Payment save).
        self.assertIsNotNone(payment.pk)
        self.assertEqual(
            InvoicePayerSharePaymentAllocation.objects.filter(
                payment=payment
            ).count(),
            0,
            "money that never arrived must not settle anyone's share",
        )
        for share in InvoicePayerShare.objects.filter(invoice=self.invoice):
            self.assertEqual(share.paid_amount, Decimal("0.00"))

    def test_a_normal_payment_still_allocates(self):
        # Guard against over-fixing: the happy path must be untouched.
        payment, paid_share = self._pay("500.00")
        self.assertEqual(paid_share.status, InvoicePayerShare.Status.PAID)
        allocation = InvoicePayerSharePaymentAllocation.objects.get(payment=payment)
        self.assertEqual(allocation.amount, Decimal("500.00"))
