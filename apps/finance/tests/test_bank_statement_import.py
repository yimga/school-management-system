from __future__ import annotations

from decimal import Decimal

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.bank_statement_import import BankStatementImportService
from apps.finance.models import (
    BankAccount,
    BankStatementEntry,
    BankStatementUpload,
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    SuspensePayment,
    SuspensePaymentAllocation,
)
from apps.people.models import StudentProfile
from apps.siteconfig.models import RegionConfig


class BankStatementImportServiceTests(TestCase):
    def setUp(self):
        self.region, _ = RegionConfig.objects.get_or_create(
            code="CMR",
            defaults={
                "name": "Cameroon",
                "default_language": "en",
                "timezone": "Africa/Douala",
            },
        )
        self.profile = ComplianceProfile.objects.create(
            name="CM Profile",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="FCFA",
            timezone="Africa/Douala",
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
            name="General", code="GEN", department=self.department
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 3",
            code="F3",
        )
        self.student = StudentProfile.objects.create(
            first_name="Moussa",
            last_name="Ibrahim",
            student_code="CMR-001",
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
            total_amount=Decimal("15000.00"),
            balance_amount=Decimal("15000.00"),
            issued_date="2026-02-01",
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=1,
            unit_price=Decimal("15000.00"),
            amount=Decimal("15000.00"),
        )
        self.bank_account = BankAccount.objects.create(
            name="Main School Account",
            account_type=BankAccount.AccountType.BANK,
            account_number="1002003004",
            bank_name="Afriland",
            currency="XAF",
            region=self.region,
            is_active=True,
        )
        self.staff = User.objects.create_superuser(
            username="finance_admin",
            password="Pass_1234",
            email="finance_admin@example.com",
        )
        self.service = BankStatementImportService()

    def test_csv_import_creates_statement_entries_and_suspense_items(self):
        csv_data = (
            "date,amount,reference,description,type,balance\n"
            "2026-02-10,15000.00,UNKNOWN-REF-001,MoMo deposit from call box,CREDIT,200000.00\n"
        )
        upload = BankStatementUpload.objects.create(
            bank_account=self.bank_account,
            statement_file=SimpleUploadedFile(
                "statement.csv", csv_data.encode("utf-8"), content_type="text/csv"
            ),
            statement_period_start="2026-02-01",
            statement_period_end="2026-02-28",
            uploaded_by=self.staff,
        )

        result = self.service.process_upload(upload)

        self.assertEqual(result["entries_created"], 1)
        self.assertEqual(result["suspense_created"], 1)
        self.assertEqual(BankStatementEntry.objects.count(), 1)
        suspense = SuspensePayment.objects.get()
        self.assertEqual(suspense.status, SuspensePayment.Status.OPEN)
        self.assertEqual(suspense.transaction_reference, "UNKNOWN-REF-001")

    def test_claim_suspense_payment_allocates_to_invoice_and_resolves(self):
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-10",
            amount=Decimal("15000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-1",
            description="Deposit without student name",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("15000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-1",
            status=SuspensePayment.Status.OPEN,
        )

        result = self.service.claim_suspense_payment(
            suspense_payment=suspense,
            allocations=[{"invoice_id": self.invoice.id, "amount": "15000.00"}],
            claimed_by=self.staff,
            notes="Matched by parent SMS confirmation",
        )

        suspense.refresh_from_db()
        self.invoice.refresh_from_db()

        self.assertEqual(result["status"], SuspensePayment.Status.RESOLVED)
        self.assertEqual(suspense.status, SuspensePayment.Status.RESOLVED)
        self.assertEqual(
            SuspensePaymentAllocation.objects.filter(suspense_payment=suspense).count(),
            1,
        )
        self.assertEqual(self.invoice.status, Invoice.Status.PAID)
        self.assertEqual(self.invoice.balance_amount, Decimal("0.00"))
