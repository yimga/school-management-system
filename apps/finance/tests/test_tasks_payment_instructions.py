from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.finance.models import BankAccount, ComplianceProfile, Invoice
from apps.finance.tasks import _get_payment_instructions
from apps.people.models import StudentProfile
from apps.siteconfig.models import RegionConfig


class PaymentInstructionsResolutionTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(
            name="Cameroon Profile",
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
        department = Department.objects.create(name="General", code="GEN")
        specialty = Specialty.objects.create(department=department, name="General", code="GEN")
        classroom = Classroom.objects.create(
            academic_year=self.year,
            department=department,
            name="Form 3",
            code="F3",
        )
        student = StudentProfile.objects.create(
            first_name="Task",
            last_name="Student",
            student_code="TASK-STUDENT-1",
            academic_year=self.year,
            classroom=classroom,
            specialty=specialty,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=student,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            issued_date=timezone.now().date(),
        )

    def test_resolves_region_from_alpha2_country_code_mapping(self):
        region, _ = RegionConfig.objects.get_or_create(
            code="CMR",
            defaults={
                "name": "Cameroon",
                "default_currency": "XAF",
                "default_language": "en",
                "timezone": "Africa/Douala",
            },
        )
        BankAccount.objects.create(
            region=region,
            name="Main Bank",
            account_type=BankAccount.AccountType.BANK,
            account_number="0001234567",
            bank_name="GTH Bank",
            branch="Buea",
            currency="XAF",
            is_active=True,
        )
        BankAccount.objects.create(
            region=region,
            name="MTN",
            account_type=BankAccount.AccountType.MTN_MOMO,
            account_number="237670000000",
            currency="XAF",
            is_active=True,
        )
        BankAccount.objects.create(
            region=region,
            name="Orange",
            account_type=BankAccount.AccountType.ORANGE_MONEY,
            account_number="237690000000",
            currency="XAF",
            is_active=True,
        )

        instructions = _get_payment_instructions(self.invoice)

        self.assertEqual(instructions["bank_account"], "0001234567")
        self.assertEqual(instructions["bank_name"], "GTH Bank")
        self.assertEqual(instructions["branch"], "Buea")
        self.assertEqual(instructions["mtn_momo_number"], "237670000000")
        self.assertEqual(instructions["orange_money_number"], "237690000000")

    def test_returns_blank_instruction_defaults_when_region_lookup_fails(self):
        with patch("apps.finance.tasks.RegionConfig.objects.filter", side_effect=RuntimeError("registry unavailable")):
            instructions = _get_payment_instructions(self.invoice)

        self.assertEqual(
            instructions,
            {
                "bank_account": "",
                "bank_name": "",
                "branch": "",
                "mtn_momo_number": "",
                "orange_money_number": "",
            },
        )
