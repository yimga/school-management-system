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
from apps.finance.services import (
    apply_payment,
    assign_equal_invoice_payer_shares,
    assign_invoice_payer_shares,
)
from apps.finance.tasks import run_payment_reminders
from apps.people.models import StudentGuardian, StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record


class SplitBillingFlowTests(TestCase):
    def setUp(self):
        self.profile = ComplianceProfile.objects.create(name="Test", country_code="CM")
        site = get_platform_site_settings_record(create=True)
        site.compliance_profile = self.profile

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

    def test_payment_reminder_reminder_channels_help_text_matches_migration_contract(self):
        # Drift guard for finance.0054_alter_paymentreminder_reminder_channels_help_text
        # and apps.finance.models.PaymentReminder.reminder_channels (admin copy).
        field = PaymentReminder._meta.get_field("reminder_channels")
        self.assertEqual(
            field.help_text,
            "Channels to use: ['email'], ['whatsapp'], ['email', 'sms'], etc. "
            "Falls back to platform default if empty.",
        )

    def test_assign_invoice_payer_shares_raises_when_split_total_mismatches_invoice(self):
        invoice = self._create_invoice()
        with self.assertRaises(ValueError) as ctx:
            assign_invoice_payer_shares(
                invoice,
                [
                    (self.guardian_link_a, Decimal("40.00")),
                    (self.guardian_link_b, Decimal("50.00")),
                ],
            )
        self.assertIn("Payer split total", str(ctx.exception))

    def test_assign_invoice_payer_shares_raises_when_guardian_student_mismatches_invoice(self):
        invoice = self._create_invoice()
        other_student = StudentProfile.objects.create(
            first_name="Other",
            last_name="Student",
            academic_year=self.year,
            student_code="SP002",
        )
        other_user = User.objects.create_user(
            username="split_parent_other",
            email="other@example.com",
            password="pass1234",
            role=User.Role.PARENT,
        )
        other_link = StudentGuardian.objects.create(
            guardian_user=other_user,
            student=other_student,
            relationship=StudentGuardian.Relationship.FATHER,
            can_view_finance=True,
        )
        with self.assertRaises(ValueError) as ctx:
            assign_invoice_payer_shares(
                invoice,
                [(other_link, Decimal("100.00"))],
            )
        self.assertIn("does not match invoice student", str(ctx.exception))

    def test_assign_invoice_payer_shares_empty_list_clears_existing_shares(self):
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [(self.guardian_link_a, Decimal("100.00"))],
        )
        self.assertEqual(
            InvoicePayerShare.objects.filter(invoice=invoice, is_active=True).count(),
            1,
        )
        assign_invoice_payer_shares(invoice, [])
        self.assertEqual(InvoicePayerShare.objects.filter(invoice=invoice).count(), 0)

    def test_assign_invoice_payer_shares_non_positive_amounts_clear_existing_shares(self):
        """Zero/negative lines are ignored; if nothing remains, active shares are cleared (batch 28 #333)."""
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [(self.guardian_link_a, Decimal("100.00"))],
        )
        self.assertEqual(
            InvoicePayerShare.objects.filter(invoice=invoice, is_active=True).count(),
            1,
        )
        assign_invoice_payer_shares(
            invoice,
            [
                (self.guardian_link_a, Decimal("0.00")),
                (self.guardian_link_b, Decimal("-1.00")),
            ],
        )
        self.assertEqual(InvoicePayerShare.objects.filter(invoice=invoice).count(), 0)

    def test_assign_equal_invoice_payer_shares_single_finance_guardian_gets_full_total(self):
        """One finance-enabled guardian receives the entire invoice total (batch 29 #348)."""
        self.guardian_link_b.can_view_finance = False
        self.guardian_link_b.save(update_fields=["can_view_finance"])
        invoice = self._create_invoice()
        rows = assign_equal_invoice_payer_shares(invoice)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].allocated_amount, Decimal("100.00"))
        self.assertEqual(rows[0].guardian_id, self.guardian_link_a.id)

    def test_assign_equal_invoice_payer_shares_returns_empty_when_no_finance_guardians(self):
        """Equal split helper returns no rows when no finance-enabled guardians (batch 30 #363)."""
        self.guardian_link_a.can_view_finance = False
        self.guardian_link_a.save(update_fields=["can_view_finance"])
        self.guardian_link_b.can_view_finance = False
        self.guardian_link_b.save(update_fields=["can_view_finance"])
        invoice = self._create_invoice()
        rows = assign_equal_invoice_payer_shares(invoice)
        self.assertEqual(rows, [])
        self.assertEqual(InvoicePayerShare.objects.filter(invoice=invoice).count(), 0)

    def test_assign_equal_invoice_payer_shares_three_guardians_splits_remainder_cents(self):
        """100.00 / 3 → 33.34 + 33.33 + 33.33 (batch 31 #378)."""
        guardian_c = User.objects.create_user(
            username="split_parent_c",
            email="split_parent_c@example.com",
            password="pass1234",
            role=User.Role.PARENT,
        )
        link_c = StudentGuardian.objects.create(
            guardian_user=guardian_c,
            student=self.student,
            relationship=StudentGuardian.Relationship.OTHER,
            can_view_finance=True,
        )
        invoice = self._create_invoice()
        rows = assign_equal_invoice_payer_shares(invoice)
        self.assertEqual(len(rows), 3)
        amounts = sorted(s.allocated_amount for s in rows)
        self.assertEqual(amounts, [Decimal("33.33"), Decimal("33.33"), Decimal("33.34")])
        guardian_ids = {s.guardian_id for s in rows}
        self.assertEqual(
            guardian_ids,
            {
                self.guardian_link_a.id,
                self.guardian_link_b.id,
                link_c.id,
            },
        )

    def test_assign_equal_invoice_payer_shares_two_guardians_splits_remainder_cents(self):
        """100.01 / 2 → 50.01 + 50.00 (batch 30 #363)."""
        invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=self.year,
            student=self.student,
            reference="INV-SPLIT-ODD",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate() + timedelta(days=5),
            total_amount=Decimal("100.01"),
            balance_amount=Decimal("100.01"),
        )
        InvoiceLine.objects.create(
            invoice=invoice,
            description="Tuition",
            quantity=Decimal("1.00"),
            unit_price=Decimal("100.01"),
            amount=Decimal("100.01"),
        )
        rows = assign_equal_invoice_payer_shares(invoice)
        self.assertEqual(len(rows), 2)
        by_amount = sorted(s.allocated_amount for s in rows)
        self.assertEqual(by_amount, [Decimal("50.00"), Decimal("50.01")])

    def test_assign_invoice_payer_shares_merges_duplicate_guardian_lines(self):
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [
                (self.guardian_link_a, Decimal("60.00")),
                (self.guardian_link_a, Decimal("40.00")),
            ],
        )
        shares = list(
            InvoicePayerShare.objects.filter(invoice=invoice).order_by("guardian_id")
        )
        self.assertEqual(len(shares), 1)
        self.assertEqual(shares[0].allocated_amount, Decimal("100.00"))

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

        share_a = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_a
        )
        share_b = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_b
        )
        self.assertEqual(share_a.paid_amount, Decimal("30.00"))
        self.assertEqual(share_a.outstanding_amount, Decimal("20.00"))
        self.assertEqual(share_a.status, InvoicePayerShare.Status.PARTIAL)
        self.assertEqual(share_b.paid_amount, Decimal("0.00"))
        self.assertEqual(share_b.outstanding_amount, Decimal("50.00"))
        self.assertEqual(share_b.status, InvoicePayerShare.Status.OPEN)

    def test_second_payment_from_other_guardian_targets_their_share(self):
        """Sequential split-billing: each payer's payment prefers their own share (batch 17 #168)."""
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [
                (self.guardian_link_a, Decimal("50.00")),
                (self.guardian_link_b, Decimal("50.00")),
            ],
            due_date=invoice.due_date,
        )

        pay_a = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("30.00"),
            method=PaymentMethodCode.CASH,
            created_by=self.guardian_a,
            paid_at=timezone.now(),
        )
        apply_payment(pay_a)

        pay_b = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("50.00"),
            method=PaymentMethodCode.CASH,
            created_by=self.guardian_b,
            paid_at=timezone.now(),
        )
        apply_payment(pay_b)

        share_a = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_a
        )
        share_b = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_b
        )
        self.assertEqual(share_a.paid_amount, Decimal("30.00"))
        self.assertEqual(share_a.outstanding_amount, Decimal("20.00"))
        self.assertEqual(share_a.status, InvoicePayerShare.Status.PARTIAL)
        self.assertEqual(share_b.paid_amount, Decimal("50.00"))
        self.assertEqual(share_b.outstanding_amount, Decimal("0.00"))
        self.assertEqual(share_b.status, InvoicePayerShare.Status.PAID)
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_amount, Decimal("20.00"))

    def test_final_payment_from_guardian_a_closes_remaining_share_and_invoice(self):
        """Split billing: after partial + full peer payment, creator can settle remainder (batch 22 #243)."""
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [
                (self.guardian_link_a, Decimal("50.00")),
                (self.guardian_link_b, Decimal("50.00")),
            ],
            due_date=invoice.due_date,
        )

        pay_a1 = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("30.00"),
            method=PaymentMethodCode.CASH,
            created_by=self.guardian_a,
            paid_at=timezone.now(),
        )
        apply_payment(pay_a1)

        pay_b = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("50.00"),
            method=PaymentMethodCode.CASH,
            created_by=self.guardian_b,
            paid_at=timezone.now(),
        )
        apply_payment(pay_b)

        pay_a2 = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("20.00"),
            method=PaymentMethodCode.CASH,
            created_by=self.guardian_a,
            paid_at=timezone.now(),
        )
        apply_payment(pay_a2)

        share_a = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_a
        )
        share_b = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_b
        )
        self.assertEqual(share_a.paid_amount, Decimal("50.00"))
        self.assertEqual(share_a.outstanding_amount, Decimal("0.00"))
        self.assertEqual(share_a.status, InvoicePayerShare.Status.PAID)
        self.assertEqual(share_b.paid_amount, Decimal("50.00"))
        self.assertEqual(share_b.outstanding_amount, Decimal("0.00"))
        self.assertEqual(share_b.status, InvoicePayerShare.Status.PAID)
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_amount, Decimal("0.00"))
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    def test_single_guardian_full_share_two_payments_closes_invoice(self):
        """Split billing: one payer with 100% share can pay in installments (batch 23 #258)."""
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [(self.guardian_link_a, Decimal("100.00"))],
            due_date=invoice.due_date,
        )

        pay1 = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("40.00"),
            method=PaymentMethodCode.CASH,
            created_by=self.guardian_a,
            paid_at=timezone.now(),
        )
        apply_payment(pay1)

        pay2 = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("60.00"),
            method=PaymentMethodCode.CASH,
            created_by=self.guardian_a,
            paid_at=timezone.now(),
        )
        apply_payment(pay2)

        share_a = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_a
        )
        self.assertEqual(share_a.paid_amount, Decimal("100.00"))
        self.assertEqual(share_a.outstanding_amount, Decimal("0.00"))
        self.assertEqual(share_a.status, InvoicePayerShare.Status.PAID)
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_amount, Decimal("0.00"))
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    def test_staff_recorded_full_payment_closes_both_shares_when_creator_not_a_guardian(
        self,
    ):
        """Staff-entered payment applies across payer shares in stable order (batch 24 #273)."""
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [
                (self.guardian_link_a, Decimal("50.00")),
                (self.guardian_link_b, Decimal("50.00")),
            ],
            due_date=invoice.due_date,
        )
        staff = User.objects.create_user(
            username="split_staff_recorder",
            email="recorder@example.com",
            password="pass1234",
            role=User.Role.ACCOUNTANT,
        )
        staff.is_staff = True
        staff.save(update_fields=["is_staff"])

        payment = Payment.objects.create(
            invoice=invoice,
            student=self.student,
            amount=Decimal("100.00"),
            method=PaymentMethodCode.CASH,
            created_by=staff,
            paid_at=timezone.now(),
        )
        apply_payment(payment)

        share_a = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_a
        )
        share_b = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_b
        )
        self.assertEqual(share_a.paid_amount, Decimal("50.00"))
        self.assertEqual(share_a.status, InvoicePayerShare.Status.PAID)
        self.assertEqual(share_b.paid_amount, Decimal("50.00"))
        self.assertEqual(share_b.status, InvoicePayerShare.Status.PAID)
        invoice.refresh_from_db()
        self.assertEqual(invoice.balance_amount, Decimal("0.00"))
        self.assertEqual(invoice.status, Invoice.Status.PAID)

    @patch("apps.finance.tasks.get_notification_channels", return_value=["email"])
    @patch("apps.finance.tasks._send_payment_email")
    def test_reminder_targets_only_guardian_with_outstanding_share(
        self, send_email_mock, _channels_mock
    ):
        invoice = self._create_invoice()
        assign_invoice_payer_shares(
            invoice,
            [
                (self.guardian_link_a, Decimal("50.00")),
                (self.guardian_link_b, Decimal("50.00")),
            ],
            due_date=timezone.localdate(),
        )
        share_a = InvoicePayerShare.objects.get(
            invoice=invoice, guardian=self.guardian_link_a
        )
        share_a.paid_amount = Decimal("50.00")
        share_a.refresh_status(save=False)
        share_a.save(update_fields=["paid_amount", "status", "updated_at"])

        reminder, _ = PaymentReminder.objects.get_or_create(invoice=invoice)
        reminder.reminder_channels = ["email"]
        reminder.reminder_days_before = [0]
        reminder.is_active = True
        reminder.next_send_at = timezone.now() - timedelta(minutes=1)
        reminder.save(
            update_fields=[
                "reminder_channels",
                "reminder_days_before",
                "is_active",
                "next_send_at",
            ]
        )

        result = run_payment_reminders()
        self.assertEqual(result["sent"], 1)
        self.assertEqual(send_email_mock.call_count, 1)
        args, _kwargs = send_email_mock.call_args
        self.assertEqual(args[0], "split_parent_b@example.com")
        self.assertIn("50.00", args[2])

    @patch("apps.finance.tasks.get_notification_channels", return_value=["email"])
    @patch(
        "apps.finance.tasks.EmailMessage.send", side_effect=SMTPException("mail failed")
    )
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
        reminder.save(
            update_fields=[
                "reminder_channels",
                "reminder_days_before",
                "is_active",
                "next_send_at",
            ]
        )

        result = run_payment_reminders()

        self.assertEqual(result["sent"], 0)
        failure_log = PaymentReminderLog.objects.filter(
            reminder=reminder, status="FAILED"
        ).latest("sent_at")
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

        # Full Client stack returns 200 but not a TemplateResponse (no response.context);
        # assert on rendered list markup instead of paginator context.
        self.client.force_login(self.guardian_a)
        parent_response = self.client.get(reverse("finance:invoices"))
        self.assertEqual(parent_response.status_code, 200)
        self.assertContains(parent_response, "INV-SPLIT-001")
        self.assertContains(parent_response, "60")  # guardian A split outstanding (formatted)

        self.client.force_login(staff)
        staff_response = self.client.get(reverse("finance:invoices"))
        self.assertEqual(staff_response.status_code, 200)
        self.assertContains(staff_response, "2 payers")
        self.assertContains(staff_response, "100")  # combined split outstanding
