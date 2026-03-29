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

    def test_claim_suspense_payment_allocates_across_two_invoices(self):
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-10",
            amount=Decimal("20000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-2",
            description="Bulk deposit",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("20000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-2",
            status=SuspensePayment.Status.OPEN,
        )
        invoice_b = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("5000.00"),
            balance_amount=Decimal("5000.00"),
            issued_date="2026-02-02",
        )
        InvoiceLine.objects.create(
            invoice=invoice_b,
            description="Fee",
            quantity=1,
            unit_price=Decimal("5000.00"),
            amount=Decimal("5000.00"),
        )

        result = self.service.claim_suspense_payment(
            suspense_payment=suspense,
            allocations=[
                {"invoice_id": self.invoice.id, "amount": "15000.00"},
                {"invoice_id": invoice_b.id, "amount": "5000.00"},
            ],
            claimed_by=self.staff,
        )

        suspense.refresh_from_db()
        self.invoice.refresh_from_db()
        invoice_b.refresh_from_db()

        self.assertEqual(result["status"], SuspensePayment.Status.RESOLVED)
        self.assertEqual(suspense.status, SuspensePayment.Status.RESOLVED)
        self.assertEqual(
            SuspensePaymentAllocation.objects.filter(suspense_payment=suspense).count(),
            2,
        )
        self.assertEqual(self.invoice.balance_amount, Decimal("0.00"))
        self.assertEqual(invoice_b.balance_amount, Decimal("0.00"))
        self.assertEqual(len(result["payment_ids"]), 2)

    def test_claim_suspense_payment_partial_allocation_sets_partial_status(self):
        """When allocated total is below suspense amount, status stays PARTIAL (batch 21 #228)."""
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-11",
            amount=Decimal("20000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-PARTIAL",
            description="Partial match deposit",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("20000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-PARTIAL",
            status=SuspensePayment.Status.OPEN,
        )
        result = self.service.claim_suspense_payment(
            suspense_payment=suspense,
            allocations=[{"invoice_id": self.invoice.id, "amount": "10000.00"}],
            claimed_by=self.staff,
        )
        suspense.refresh_from_db()
        self.assertEqual(result["status"], SuspensePayment.Status.PARTIAL)
        self.assertEqual(suspense.status, SuspensePayment.Status.PARTIAL)
        self.assertGreater(suspense.remaining_amount, Decimal("0.00"))
        self.assertEqual(
            SuspensePaymentAllocation.objects.filter(suspense_payment=suspense).count(),
            1,
        )

    def test_claim_suspense_payment_empty_allocations_raises(self):
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-12",
            amount=Decimal("5000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-EMPTY-ALLOC",
            description="Empty alloc test",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("5000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-EMPTY-ALLOC",
            status=SuspensePayment.Status.OPEN,
        )
        with self.assertRaises(ValueError) as ctx:
            self.service.claim_suspense_payment(
                suspense_payment=suspense,
                allocations=[],
                claimed_by=self.staff,
            )
        self.assertIn("At least one allocation", str(ctx.exception))

    def test_claim_suspense_payment_total_exceeds_remaining_raises(self):
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-13",
            amount=Decimal("8000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-OVER",
            description="Over-alloc test",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("8000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-OVER",
            status=SuspensePayment.Status.OPEN,
        )
        with self.assertRaises(ValueError) as ctx:
            self.service.claim_suspense_payment(
                suspense_payment=suspense,
                allocations=[{"invoice_id": self.invoice.id, "amount": "9000.00"}],
                claimed_by=self.staff,
            )
        self.assertIn("exceeds suspense remaining", str(ctx.exception))

    def test_claim_suspense_payment_non_positive_allocation_total_raises(self):
        """Batch 33 #408: zero/negative line amounts contribute nothing; total must stay positive."""
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-15",
            amount=Decimal("1000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-ZERO-ALLOC",
            description="Non-positive allocation test",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("1000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-ZERO-ALLOC",
            status=SuspensePayment.Status.OPEN,
        )
        with self.assertRaises(ValueError) as ctx:
            self.service.claim_suspense_payment(
                suspense_payment=suspense,
                allocations=[
                    {"invoice_id": self.invoice.id, "amount": "0.00"},
                    {"invoice_id": self.invoice.id, "amount": "-10.00"},
                ],
                claimed_by=self.staff,
            )
        self.assertIn("Allocation total must be positive", str(ctx.exception))

    def test_claim_suspense_payment_duplicate_invoice_in_allocations_raises(self):
        """Batch 34 #423: same invoice twice must not create double payments."""
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-16",
            amount=Decimal("5000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-DUP-INV",
            description="Duplicate invoice id in payload",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("5000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-DUP-INV",
            status=SuspensePayment.Status.OPEN,
        )
        with self.assertRaises(ValueError) as ctx:
            self.service.claim_suspense_payment(
                suspense_payment=suspense,
                allocations=[
                    {"invoice_id": self.invoice.id, "amount": "2000.00"},
                    {"invoice_id": self.invoice.id, "amount": "3000.00"},
                ],
                claimed_by=self.staff,
            )
        self.assertIn("Duplicate invoice_id", str(ctx.exception))

    def test_claim_suspense_payment_invalid_amount_string_raises(self):
        """Batch 35 #438: non-numeric allocation amount must surface as ValueError."""
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-17",
            amount=Decimal("4000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-BAD-AMT",
            description="Invalid decimal in allocation",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("4000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-BAD-AMT",
            status=SuspensePayment.Status.OPEN,
        )
        with self.assertRaises(ValueError) as ctx:
            self.service.claim_suspense_payment(
                suspense_payment=suspense,
                allocations=[{"invoice_id": self.invoice.id, "amount": "not-a-number"}],
                claimed_by=self.staff,
            )
        self.assertIn("Invalid amount", str(ctx.exception))

    def test_claim_suspense_payment_ignores_zero_row_when_second_invoice_positive(self):
        """Batch 35 #438: non-positive lines are skipped; a second positive line still allocates."""
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-17",
            amount=Decimal("8000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-ZERO-PLUS-POS",
            description="Zero row plus positive second invoice",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("8000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-ZERO-PLUS-POS",
            status=SuspensePayment.Status.OPEN,
        )
        invoice_b = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("8000.00"),
            balance_amount=Decimal("8000.00"),
            issued_date="2026-02-03",
        )
        InvoiceLine.objects.create(
            invoice=invoice_b,
            description="Second fee",
            quantity=1,
            unit_price=Decimal("8000.00"),
            amount=Decimal("8000.00"),
        )
        result = self.service.claim_suspense_payment(
            suspense_payment=suspense,
            allocations=[
                {"invoice_id": self.invoice.id, "amount": "0.00"},
                {"invoice_id": invoice_b.id, "amount": "8000.00"},
            ],
            claimed_by=self.staff,
        )
        suspense.refresh_from_db()
        invoice_b.refresh_from_db()
        self.assertEqual(result["status"], SuspensePayment.Status.RESOLVED)
        self.assertEqual(invoice_b.balance_amount, Decimal("0.00"))
        self.assertEqual(
            SuspensePaymentAllocation.objects.filter(suspense_payment=suspense).count(),
            1,
        )

    def test_claim_suspense_payment_unknown_invoice_raises(self):
        statement = BankStatementEntry.objects.create(
            bank_account=self.bank_account,
            transaction_date="2026-02-14",
            amount=Decimal("3000.00"),
            transaction_type=BankStatementEntry.TransactionType.DEPOSIT,
            transaction_reference="BANK-TXN-BAD-INV",
            description="Bad invoice id test",
        )
        suspense = SuspensePayment.objects.create(
            bank_statement_entry=statement,
            amount=Decimal("3000.00"),
            currency="XAF",
            transaction_reference="BANK-TXN-BAD-INV",
            status=SuspensePayment.Status.OPEN,
        )
        missing_id = self.invoice.id + 99999
        with self.assertRaises(Invoice.DoesNotExist):
            self.service.claim_suspense_payment(
                suspense_payment=suspense,
                allocations=[{"invoice_id": missing_id, "amount": "1000.00"}],
                claimed_by=self.staff,
            )
