from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    JournalEntry,
    JournalLine,
    LedgerAccount,
    Payment,
    PaymentMethodCode,
    SuspensePayment,
)
from apps.finance.ohada_reports import build_dsf_report
from apps.people.models import StudentProfile


class OhadaReportTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="CM Test", country_code="CM"
        )
        self.asset_cash = LedgerAccount.objects.create(
            profile=self.profile,
            code="57",
            name="Cash and bank",
            account_type=LedgerAccount.AccountType.ASSET,
        )
        self.equity = LedgerAccount.objects.create(
            profile=self.profile,
            code="10",
            name="Capital",
            account_type=LedgerAccount.AccountType.EQUITY,
        )
        self.revenue = LedgerAccount.objects.create(
            profile=self.profile,
            code="701",
            name="Tuition revenue",
            account_type=LedgerAccount.AccountType.INCOME,
        )
        self.expense = LedgerAccount.objects.create(
            profile=self.profile,
            code="601",
            name="Supplies expense",
            account_type=LedgerAccount.AccountType.EXPENSE,
        )

        entry = JournalEntry.objects.create(
            profile=self.profile,
            entry_date=date(2026, 1, 10),
            posted_at=timezone.now(),
            source_type="test",
        )
        JournalLine.objects.create(
            entry=entry,
            account=self.asset_cash,
            debit=Decimal("1000.00"),
            credit=Decimal("0.00"),
        )
        JournalLine.objects.create(
            entry=entry,
            account=self.revenue,
            debit=Decimal("0.00"),
            credit=Decimal("1000.00"),
        )

        entry2 = JournalEntry.objects.create(
            profile=self.profile,
            entry_date=date(2026, 1, 12),
            posted_at=timezone.now(),
            source_type="test",
        )
        JournalLine.objects.create(
            entry=entry2,
            account=self.expense,
            debit=Decimal("200.00"),
            credit=Decimal("0.00"),
        )
        JournalLine.objects.create(
            entry=entry2,
            account=self.asset_cash,
            debit=Decimal("0.00"),
            credit=Decimal("200.00"),
        )

        entry3 = JournalEntry.objects.create(
            profile=self.profile,
            entry_date=date(2026, 1, 14),
            posted_at=timezone.now(),
            source_type="test",
        )
        JournalLine.objects.create(
            entry=entry3,
            account=self.asset_cash,
            debit=Decimal("500.00"),
            credit=Decimal("0.00"),
        )
        JournalLine.objects.create(
            entry=entry3,
            account=self.equity,
            debit=Decimal("0.00"),
            credit=Decimal("500.00"),
        )

        year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        department = Department.objects.create(name="General", code="GEN-OHADA")
        specialty = Specialty.objects.create(
            name="General Studies", code="GEN-OHADA", department=department
        )
        classroom = Classroom.objects.create(
            academic_year=year,
            department=department,
            name="Form 2",
            code="F2-OHADA",
        )
        student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            student_code="OH-001",
            academic_year=year,
            classroom=classroom,
            specialty=specialty,
        )
        invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=year,
            student=student,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.PARTIAL,
            issued_date=date(2026, 1, 10),
            due_date=date(2026, 1, 25),
            total_amount=Decimal("50000.00"),
            balance_amount=Decimal("25000.00"),
            reference="INV-OHADA-01",
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal("50000.00"),
            amount=Decimal("50000.00"),
        )
        Payment.objects.create(
            invoice=invoice,
            student=student,
            amount=Decimal("25000.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
            paid_at=timezone.make_aware(datetime(2026, 1, 15, 10, 0, 0)),
            receipt_number="RCPT-1",
        )
        suspense = SuspensePayment.objects.create(
            amount=Decimal("4000.00"),
            currency="XAF",
            transaction_reference="SUSP-1",
            status=SuspensePayment.Status.OPEN,
        )
        SuspensePayment.objects.filter(pk=suspense.pk).update(
            created_at=timezone.make_aware(datetime(2026, 1, 15, 9, 0, 0))
        )

    def test_build_dsf_report_returns_expected_sections(self):
        report = build_dsf_report(
            profile=self.profile,
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )

        # Revenue is ledger-driven and includes both manual journal revenue (1,000)
        # and posted invoice revenue (50,000) from the invoice setup in this test.
        self.assertEqual(report.income_statement["revenue_total"], Decimal("51000.00"))
        self.assertEqual(report.income_statement["expense_total"], Decimal("200.00"))
        self.assertEqual(report.income_statement["net_result"], Decimal("50800.00"))
        self.assertEqual(report.cash_flow["cash_in"], Decimal("25000.00"))
        self.assertEqual(report.annexes["payment_count"], 1)
        self.assertEqual(report.annexes["unresolved_suspense_count"], 1)
        self.assertGreaterEqual(
            report.annexes["estimated_stamp_duty_xaf"], Decimal("1000.00")
        )
