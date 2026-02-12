"""Tests for split payment allocation flow."""
from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear
from apps.finance.models import ComplianceProfile, Invoice, InvoiceLine, Payment
from apps.people.models import StudentProfile
from apps.siteconfig.models import SiteSettings


class SplitAllocationTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(name="Test", country_code="CM")
        site = SiteSettings.get_solo()
        site.compliance_profile = self.profile
        site.save(update_fields=["compliance_profile"])
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            first_name="Test",
            last_name="Student",
            academic_year=self.year,
            student_code="ST001",
        )
        self.staff = User.objects.create_user(
            username="staff_split",
            password="pass1234",
            role=User.Role.ACCOUNTANT,
        )
        self.staff.is_staff = True
        self.staff.save(update_fields=["is_staff"])

    def test_split_allocation_creates_invoice_and_payment(self):
        self.client.force_login(self.staff)
        total = Decimal("50000.00")
        self.client.get(reverse("finance:split_allocation"))  # load form so session has CSRF
        post_data = {
            "student": self.student.id,
            "total_amount": str(total),
            "method": "CASH",
            "desc_1": "Tuition",
            "amount_1": str(total),
            "desc_2": "",
            "amount_2": "0",
            "amount_3": "0",
            "amount_4": "0",
            "amount_5": "0",
        }
        response = self.client.post(reverse("finance:split_allocation"), post_data)
        self.assertEqual(response.status_code, 302)
        invoice = Invoice.objects.filter(student=self.student, reference__startswith="SPLIT-").order_by("-id").first()
        self.assertIsNotNone(invoice)
        self.assertEqual(invoice.student_id, self.student.id)
        self.assertEqual(invoice.total_amount, total)
        self.assertEqual(invoice.lines.count(), 1)
        line = invoice.lines.get()
        self.assertEqual(line.description, "Tuition")
        self.assertEqual(line.amount, total)
        payment = Payment.objects.get(invoice=invoice)
        self.assertEqual(payment.amount, total)
        self.assertEqual(payment.method, "CASH")
        # Optional assert: payment was applied (invoice balance updated)
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_amount, Decimal("0.00"), "Invoice balance should be zero after full payment")
