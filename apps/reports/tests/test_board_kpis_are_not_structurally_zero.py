"""The executive/board finance KPIs must report real money.

Found by an A-Z audit follow-up (2026-07-16).

``ExecutiveReportingService.get_financial_summary`` filtered on status values
that do not exist on the models it queries::

    payments = Payment.objects.filter(..., status="COMPLETED")
    outstanding = invoices.filter(status="PENDING").aggregate(Sum("total_amount"))

``Payment.status`` choices are entirely LOWERCASE (pending / processing /
completed / failed / cancelled / refunded) and ``Invoice.Status`` has no
PENDING member at all (DRAFT / ISSUED / PARTIAL / PAID / OVERDUE / VOID). Both
filters therefore matched zero rows BY CONSTRUCTION, so ``total_collected``,
``payment_count``, ``outstanding`` and ``collection_rate`` were pinned to 0
for every school, in every period, no matter how much money moved.

This is not a dormant code path: ``board_aggregation_kernel
.refresh_board_kpi_snapshot`` persists the result to
``school.settings["board_reporting"]``, and it is wired to the
``institutional_performance_board_reporting`` setup wizard. A board could read
"collected: 0, collection rate: 0%" off a full book of paid invoices.

The rest of the codebase already had it right -- ``observability/views.py`` and
``api/serializers.py`` both filter ``status="completed"``. bi_services was the
lone outlier, which is what a literal written from memory looks like.

Semantics pinned here (they were previously unstated, and 0 hid the question):
  * collected  = payments that actually completed, net of refunds, excluding
    soft-deleted rows -- money truly received.
  * billed     = invoices excluding DRAFT (never issued) and VOID (never owed).
  * outstanding= unpaid balance on those billed invoices.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
)
from apps.finance.services import recalculate_invoice
from apps.people.models import StudentProfile
from apps.reports.bi_services import ExecutiveReportingService
from apps.schools.models import School


class _BoardKPIFixture(TestCase):
    """Shared seed: one school, one student, a compliance profile."""

    def _seed(self, slug: str):
        self.school = School.objects.create(
            name=f"{slug} High", slug=slug, subdomain=slug
        )
        self.profile = ComplianceProfile.objects.create(
            name=f"Default {slug}", country_code="CM"
        )
        self.student = StudentProfile.objects.create(
            school=self.school, first_name="Kay", last_name="Pea",
            student_code=f"{slug}-1",
        )
        self.start = timezone.now() - timedelta(days=30)
        self.end = timezone.now() + timedelta(days=1)

    def _invoice(self, *, total, status, school=None, student=None,
                 profile=None):
        """Build an invoice the way the domain does: from a line.

        ``total_amount``/``balance_amount`` are DERIVED -- ``recalculate_invoice``
        sums InvoiceLine rows and re-syncs the balance, and it fires on payment
        sync. An invoice hand-stamped with a total but no lines silently
        collapses to 0.00/DRAFT the moment a Payment lands on it.
        """
        invoice = Invoice.objects.create(
            school=school or self.school,
            profile=profile or self.profile,
            student=student or self.student,
            total_amount=Decimal(total),
            balance_amount=Decimal(total),
            status=status,
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal(total),
            amount=Decimal(total),
        )
        recalculate_invoice(invoice)
        invoice.refresh_from_db()
        if invoice.status != status:
            Invoice.objects.filter(pk=invoice.pk).update(status=status)  # tenant-isolation-allow: test-fixture-pins-derived-status-by-pk
            invoice.refresh_from_db()
        return invoice

    def _summary(self):
        return ExecutiveReportingService.get_financial_summary(
            self.start, self.end, school_id=str(self.school.pk)
        )


class BoardFinanceKPIsTests(_BoardKPIFixture):
    """A school with real money must not report zeros."""

    def setUp(self):
        self._seed("kpi-high")
        # Billed 1000, paid 400 -> outstanding 600, collection rate 40%.
        self.invoice = self._invoice(
            total="1000.00", status=Invoice.Status.PARTIAL,
        )
        Payment.objects.create(
            school=self.school,
            invoice=self.invoice,
            amount=Decimal("400.00"),
            status="completed",
            method="CASH",
        )

    def test_collected_is_not_structurally_zero(self):
        summary = self._summary()
        self.assertEqual(
            Decimal(str(summary["total_collected"])), Decimal("400.00"),
            "a completed payment was invisible to the board -- the filter used "
            "status='COMPLETED' but Payment's choices are lowercase",
        )

    def test_payment_count_sees_the_payment(self):
        self.assertEqual(self._summary()["payment_count"], 1)

    def test_outstanding_is_not_structurally_zero(self):
        summary = self._summary()
        self.assertEqual(
            Decimal(str(summary["outstanding"])), Decimal("600.00"),
            "outstanding filtered on Invoice status='PENDING', which is not a "
            "member of Invoice.Status at all",
        )

    def test_collection_rate_is_real(self):
        self.assertAlmostEqual(self._summary()["collection_rate"], 40.0, places=1)


class BoardKPIMoneySemanticsTests(_BoardKPIFixture):
    """The edges that decide whether a number is honest."""

    def setUp(self):
        self._seed("sem-high")
        self.invoice = self._invoice(
            total="1000.00", status=Invoice.Status.ISSUED,
        )

    def test_a_failed_payment_is_not_collected_money(self):
        Payment.objects.create(
            school=self.school, invoice=self.invoice,
            amount=Decimal("500.00"), status="failed", method="CASH",
        )
        self.assertEqual(Decimal(str(self._summary()["total_collected"])),
                         Decimal("0.00"))

    def test_a_pending_payment_is_not_collected_money(self):
        Payment.objects.create(
            school=self.school, invoice=self.invoice,
            amount=Decimal("500.00"), status="pending", method="CASH",
        )
        self.assertEqual(Decimal(str(self._summary()["total_collected"])),
                         Decimal("0.00"))

    def test_a_refund_reduces_collected(self):
        Payment.objects.create(
            school=self.school, invoice=self.invoice,
            amount=Decimal("500.00"), refunded_amount=Decimal("200.00"),
            status="completed", method="CASH",
        )
        self.assertEqual(
            Decimal(str(self._summary()["total_collected"])), Decimal("300.00"),
            "money handed back is not money collected",
        )

    def test_a_void_invoice_is_not_billed_or_outstanding(self):
        self._invoice(total="9999.00", status=Invoice.Status.VOID)
        summary = self._summary()
        self.assertEqual(Decimal(str(summary["total_invoiced"])),
                         Decimal("1000.00"),
                         "a voided invoice was never owed")
        self.assertEqual(Decimal(str(summary["outstanding"])),
                         Decimal("1000.00"))

    def test_a_draft_invoice_is_not_billed(self):
        self._invoice(total="5555.00", status=Invoice.Status.DRAFT)
        self.assertEqual(Decimal(str(self._summary()["total_invoiced"])),
                         Decimal("1000.00"),
                         "a draft invoice was never issued to anyone")

    def test_another_schools_money_never_leaks_in(self):
        other = School.objects.create(
            name="Other KPI", slug="kpi-other", subdomain="kpi-other"
        )
        other_student = StudentProfile.objects.create(
            school=other, first_name="Oth", last_name="Er",
            student_code="OTH-1",
        )
        other_invoice = self._invoice(
            total="7777.00", status=Invoice.Status.ISSUED,
            school=other, student=other_student,
        )
        Payment.objects.create(
            school=other, invoice=other_invoice,
            amount=Decimal("7777.00"), status="completed", method="CASH",
        )
        summary = self._summary()
        self.assertEqual(Decimal(str(summary["total_invoiced"])),
                         Decimal("1000.00"))
        self.assertEqual(Decimal(str(summary["total_collected"])),
                         Decimal("0.00"))
