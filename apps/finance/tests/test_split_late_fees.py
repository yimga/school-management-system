from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicYear
from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine, InvoicePayerShare
from apps.finance.services import assign_invoice_payer_shares
from apps.finance.tasks import run_split_late_fees
from apps.people.models import StudentGuardian, StudentProfile
from apps.siteconfig.models import SiteSettings


class SplitLateFeeTaskTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(name="Split Late Fee", country_code="CM")
        site = SiteSettings.get_solo()
        site.compliance_profile = self.profile
        site.backend_feature_flags = {
            **(site.backend_feature_flags or {}),
            "finance_split_late_fee_enabled": True,
            "finance_split_late_fee_grace_days": 1,
            "finance_split_late_fee_mode": "percentage",
            "finance_split_late_fee_percent": "2.00",
            "finance_split_late_fee_cap_percent": "20.00",
        }
        site.save(update_fields=["compliance_profile", "backend_feature_flags"])

        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            first_name="Late",
            last_name="Fee",
            academic_year=self.year,
            student_code="LF001",
        )
        guardian_user = User.objects.create_user(
            username="late_fee_guardian",
            email="late_fee_guardian@example.com",
            password="pass1234",
            role=User.Role.PARENT,
        )
        self.guardian_link = StudentGuardian.objects.create(
            guardian_user=guardian_user,
            student=self.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
            can_view_finance=True,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            student=self.student,
            reference="INV-LATE-001",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate() - timedelta(days=10),
            due_date=timezone.localdate() - timedelta(days=5),
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            amount=Decimal("100.00"),
        )
        assign_invoice_payer_shares(
            self.invoice,
            [(self.guardian_link, Decimal("100.00"))],
            due_date=self.invoice.due_date,
        )

    def test_run_split_late_fees_applies_fee_and_invoice_line(self):
        result = run_split_late_fees()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["applied"], 1)
        self.assertEqual(result["total_fee"], Decimal("2.00"))

        share = InvoicePayerShare.objects.get(invoice=self.invoice, guardian=self.guardian_link)
        self.assertEqual(share.late_fee_amount, Decimal("2.00"))
        self.assertIsNotNone(share.last_late_fee_applied_at)

        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.total_amount, Decimal("102.00"))
        self.assertEqual(self.invoice.balance_amount, Decimal("102.00"))
        self.assertEqual(self.invoice.lines.filter(description__startswith="Late fee (").count(), 1)

    def test_run_split_late_fees_is_idempotent_same_day(self):
        first = run_split_late_fees()
        second = run_split_late_fees()
        self.assertEqual(first["applied"], 1)
        self.assertEqual(second["applied"], 0)
        self.assertEqual(second["total_fee"], Decimal("0.00"))

        share = InvoicePayerShare.objects.get(invoice=self.invoice, guardian=self.guardian_link)
        self.assertEqual(share.late_fee_amount, Decimal("2.00"))
        self.assertEqual(self.invoice.lines.filter(description__startswith="Late fee (").count(), 1)
