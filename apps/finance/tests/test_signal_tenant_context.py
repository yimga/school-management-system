from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, tag

from apps.finance.models import ComplianceProfile, Invoice, PaymentReminder
from apps.finance.signals import _deactivate_reminders_for_student
from apps.people.models import StudentProfile
from apps.schools.models import School
from apps.schools.rls_context import rls_bypass


@tag("tenants_rls")
class FinanceSignalTenantContextTests(TestCase):
    def test_deactivate_reminders_resolves_school_from_invoice_when_student_missing_school(self):
        with rls_bypass():
            school = School.objects.create(
                name="Reminder School",
                slug="reminder-school",
                subdomain="reminder-school",
                is_active=True,
            )
            profile = ComplianceProfile.objects.create(
                name="Default Finance",
                country_code="US",
                currency_code="USD",
                currency_symbol="$",
                is_active=True,
            )
            student = StudentProfile.objects.create(
                school=None,
                first_name="No",
                last_name="School",
                student_code="NO-SCHOOL-1",
            )
            invoice = Invoice.objects.create(
                school=school,
                profile=profile,
                student=student,
                total_amount=Decimal("100.00"),
                balance_amount=Decimal("100.00"),
                status=Invoice.Status.ISSUED,
            )
            reminder = PaymentReminder.objects.create(invoice=invoice, is_active=True)

        with patch("apps.finance.signals._requires_explicit_rls_context", return_value=True):
            self.assertEqual(_deactivate_reminders_for_student(student), 1)

        with rls_bypass():
            reminder.refresh_from_db()
            self.assertFalse(reminder.is_active)
