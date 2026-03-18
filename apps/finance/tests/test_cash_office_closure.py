from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import (
    CashOfficeClosure,
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    Payment,
    PaymentMethodCode,
)
from apps.people.models import StudentProfile


class CashOfficeClosureTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon Finance",
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
            department=self.department,
            name="General",
            code="GEN",
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 3",
            code="F3",
        )
        self.student = StudentProfile.objects.create(
            first_name="Abajo",
            last_name="Jeffter",
            student_code="STU-CASH-001",
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
            total_amount=Decimal("50000.00"),
            balance_amount=Decimal("50000.00"),
            issued_date=timezone.localdate(),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal("50000.00"),
            amount=Decimal("50000.00"),
        )
        self.user = User.objects.create_superuser(
            username="cashadmin",
            email="cashadmin@example.com",
            password="Pass_1234",
        )
        self.client.login(username="cashadmin", password="Pass_1234")

    def test_cash_office_closure_view_creates_expected_reconciliation(self):
        Payment.objects.create(
            invoice=self.invoice,
            student=self.student,
            amount=Decimal("10000.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
            paid_at=timezone.now(),
            physical_receipt_book_serial="RCPT-2026-A",
            physical_receipt_number=1,
        )

        response = self.client.post(
            reverse("finance:cash_office_closure"),
            data={
                "closure_date": timezone.localdate().isoformat(),
                "opening_cash": "2000",
                "deposited_to_bank": "8000",
                "cash_on_hand": "4000",
                "deposit_reference": "BNK-CLOSE-001",
                "notes": "Daily closure",
            },
        )
        self.assertEqual(response.status_code, 302)

        closure = CashOfficeClosure.objects.get(
            profile=self.profile, closure_date=timezone.localdate()
        )
        self.assertEqual(closure.cash_collected, Decimal("10000.00"))
        self.assertEqual(closure.expected_cash, Decimal("4000.00"))
        self.assertEqual(closure.discrepancy, Decimal("0.00"))
        self.assertEqual(closure.status, CashOfficeClosure.Status.CLOSED)

    def test_physical_receipt_serial_validation_and_uniqueness(self):
        Payment.objects.create(
            invoice=self.invoice,
            student=self.student,
            amount=Decimal("5000.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
            paid_at=timezone.now(),
            physical_receipt_book_serial="BOOK-A",
            physical_receipt_number=17,
        )

        invalid_non_cash = Payment(
            invoice=self.invoice,
            student=self.student,
            amount=Decimal("2000.00"),
            method=PaymentMethodCode.BANK,
            status="completed",
            paid_at=timezone.now(),
            physical_receipt_book_serial="BOOK-A",
            physical_receipt_number=18,
        )
        with self.assertRaises(ValidationError):
            invalid_non_cash.full_clean()

        duplicate_cash = Payment(
            invoice=self.invoice,
            student=self.student,
            amount=Decimal("1000.00"),
            method=PaymentMethodCode.CASH,
            status="completed",
            paid_at=timezone.now(),
            physical_receipt_book_serial="BOOK-A",
            physical_receipt_number=17,
        )
        with self.assertRaises(ValidationError):
            duplicate_cash.full_clean()
