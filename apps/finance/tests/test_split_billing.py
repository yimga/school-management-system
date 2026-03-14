from datetime import date, timedelta
from decimal import Decimal
from smtplib import SMTPException
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicYear
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    InvoicePayerShare,
    Payment,
    PaymentMethodCode,
    PaymentReminder,
    PaymentReminderLog,
)
from apps.finance.services import apply_payment, assign_invoice_payer_shares
from apps.finance.tasks import run_payment_reminders
from apps.people.models import StudentGuardian, StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record


class SplitBillingFlowTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(name="Test", country_code="CM")
        site = get_platform_site_settings_record(create=True)
        site.compliance_profile = self.profile
        site.save(update_fields=["compliance_profile_id"])

        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            first_name="Split",
            last_name="Student",
            academic_year=self.year,
            student_code="SP001",
        )
        self.guardian_a = User.objects.create_user(
            username="split_parent_a",
            email="split_parent_a@example.com",
            password="pass1234",
            role=User.Role.PARENT,
        )
        self.guardian_b = User.objects.create_user(
            username="split_parent_b",
            email="split_parent_b@example.com",
            password="pass1234",
            role=User.Role.PARENT,
        )
        self.guardian_link_a = StudentGuardian.objects.create(
            guardian_user=self.guardian_a,
            student=self.student,
            relationship=StudentGuardian.Relationship.FATHER,
            can_view_finance=True,
        )
        self.guardian_link_b = StudentGuardian.objects.create(
            guardian_user=self.guardian_b,
            student=self.student,
            relationship=StudentGuardian.Relationship.MOTHER,
            can_view_finance=True,
        )

    def _create_invoice(self) -> Invoice:
        invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            student=self.student,
            reference="INV-SPLIT-001",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=5),
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.00"),
            amount=Decimal("100.00"),
        )
        return invoice

    def test_apply_payment_prefers_creator_guardian_share(self):
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [
                (self.guardian_link_a, Decimal("50.00")),
                (self.guardian_link_b, Decimal("50.00")),
            ],
            due_date=invoice.due_date,
        )

        payment = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("30.00"),
            method=PaymentMethodCode.CASH,
            created_by=self.guardian_a,
            paid_at=timezone.now(),
        )
        apply_payment(payment)

        share_a = InvoicePayerShare.objects.get(invoice=invoice, guardian=self.guardian_link_a)
        share_b = InvoicePayerShare.objects.get(invoice=invoice, guardian=self.guardian_link_b)
        self.assertEqual(share_a.paid_amount, Decimal("30.00"))
        self.assertEqual(share_a.outstanding_amount, Decimal("20.00"))
        self.assertEqual(share_a.status, InvoicePayerShare.Status.PARTIAL)
        self.assertEqual(share_b.paid_amount, Decimal("0.00"))
        self.assertEqual(share_b.outstanding_amount, Decimal("50.00"))
        self.assertEqual(share_b.status, InvoicePayerShare.Status.OPEN)

    @patch("apps.finance.tasks.get_notification_channels", return_value=["email"])
    @patch("apps.finance.tasks._send_payment_email")
    def test_reminder_targets_only_guardian_with_outstanding_share(self, send_email_mock, _channels_mock):
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [
                (self.guardian_link_a, Decimal("50.00")),
                (self.guardian_link_b, Decimal("50.00")),
            ],
            due_date=timezone.localdate(),
        )
        share_a = InvoicePayerShare.objects.get(invoice=invoice, guardian=self.guardian_link_a)
        share_a.paid_amount = Decimal("50.00")
        share_a.refresh_status(save=False)
        share_a.save(update_fields=["paid_amount", "status", "updated_at"])

        reminder, _ = PaymentReminder.objects.get_or_create(invoice=invoice)
        reminder.reminder_channels = ["email"]
        reminder.reminder_days_before = [0]
        reminder.is_active = True
        reminder.next_send_at = timezone.now() - timedelta(minutes=1)
        reminder.save(update_fields=["reminder_channels", "reminder_days_before", "is_active", "next_send_at"])

        result = run_payment_reminders()
        self.assertEqual(result["sent"], 1)
        self.assertEqual(send_email_mock.call_count, 1)
        args, _kwargs = send_email_mock.call_args
        self.assertEqual(args[0], "split_parent_b@example.com")
        self.assertIn("50.00", args[2])

    @patch("apps.finance.tasks.get_notification_channels", return_value=["email"])
    @patch("apps.finance.tasks.EmailMessage.send", side_effect=SMTPException("mail failed"))
    def test_reminder_logs_failed_email_delivery(self, _send_mock, _channels_mock):
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [(self.guardian_link_a, Decimal("100.00"))],
            due_date=timezone.localdate(),
        )
        reminder, _ = PaymentReminder.objects.get_or_create(invoice=invoice)
        reminder.reminder_channels = ["email"]
        reminder.reminder_days_before = [0]
        reminder.is_active = True
        reminder.next_send_at = timezone.now() - timedelta(minutes=1)
        reminder.save(update_fields=["reminder_channels", "reminder_days_before", "is_active", "next_send_at"])

        result = run_payment_reminders()

        self.assertEqual(result["sent"], 0)
        failure_log = PaymentReminderLog.objects.filter(reminder=reminder, status="FAILED").latest("sent_at")
        self.assertIn("Failed to send email", failure_log.note)

    def test_invoice_list_exposes_split_summary_for_parent_and_staff(self):
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [
                (self.guardian_link_a, Decimal("60.00")),
                (self.guardian_link_b, Decimal("40.00")),
            ],
            due_date=invoice.due_date,
        )

        staff = User.objects.create_user(
            username="split_staff",
            email="split_staff@example.com",
            password="pass1234",
            role=User.Role.ACCOUNTANT,
        )
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])

        self.client.force_login(self.guardian_a)
        parent_response = self.client.get(reverse("finance:invoices"))
        self.assertEqual(parent_response.status_code, 200)
        parent_inv = parent_response.context["invoices"].object_list[0]
        self.assertEqual(parent_inv.my_split_outstanding, Decimal("60.00"))
        self.assertEqual(parent_inv.split_payer_count, 2)

        self.client.force_login(staff)
        staff_response = self.client.get(reverse("finance:invoices"))
        self.assertEqual(staff_response.status_code, 200)
        staff_inv = staff_response.context["invoices"].object_list[0]
        self.assertEqual(staff_inv.split_payer_count, 2)
        self.assertEqual(staff_inv.split_outstanding_total, Decimal("100.00"))
