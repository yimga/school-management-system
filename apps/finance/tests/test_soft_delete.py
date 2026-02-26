from decimal import Decimal

from django.test import TestCase

from apps.finance.models import ComplianceProfile, Invoice, Payment
from apps.people.models import StudentProfile
from apps.schools.models import School


class FinanceSoftDeleteTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Finance Soft Delete School",
            slug="finance-soft-delete-school",
            subdomain="finance-soft-delete-school",
            is_active=True,
        )
        self.profile = ComplianceProfile.objects.create(
            name="Finance Profile",
            country_code="US",
            currency_code="USD",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Fin",
            last_name="Student",
            is_active=True,
        )

    def test_invoice_delete_soft_deletes_and_marks_void(self):
        invoice = Invoice.objects.create(
            school=self.school,
            profile=self.profile,
            student=self.student,
            status=Invoice.Status.ISSUED,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            reference="INV-SOFT-1",
        )
        invoice_id = invoice.pk

        deleted_count, _ = invoice.delete()

        self.assertEqual(deleted_count, 1)
        self.assertTrue(Invoice.objects.filter(pk=invoice_id).exists())
        invoice.refresh_from_db()
        self.assertIsNotNone(invoice.deleted_at)
        self.assertEqual(invoice.status, Invoice.Status.VOID)

    def test_payment_delete_soft_deletes_and_marks_cancelled(self):
        payment = Payment.objects.create(
            school=self.school,
            student=self.student,
            amount=Decimal("20.00"),
            currency_code="USD",
            purpose="tuition",
            method="BANK",
            status="completed",
        )
        payment_id = payment.pk

        deleted_count, _ = payment.delete()

        self.assertEqual(deleted_count, 1)
        self.assertTrue(Payment.objects.filter(pk=payment_id).exists())
        payment.refresh_from_db()
        self.assertIsNotNone(payment.deleted_at)
        self.assertEqual(payment.status, "cancelled")
