"""Tests for Pay with wallet checkout (ParentWallet / WalletTransaction)."""

from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicYear
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    ParentWallet,
    PaymentMethodCode,
    WalletTransaction,
)
from apps.finance.services import pay_invoice_with_wallet, top_up_wallet
from apps.people.models import StudentProfile
from apps.schools.models import School


class PayWithWalletTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(name="Test School", is_active=True)
        self.profile = ComplianceProfile.objects.create(name="Test", country_code="CM")
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            first_name="W",
            last_name="Student",
            academic_year=self.year,
            student_code="W001",
            school=self.school,
        )
        self.user = User.objects.create_user(
            username="parent_wallet",
            email="parent_w@example.com",
            password="pass",
            role=User.Role.PARENT,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            academic_year=self.year,
            student=self.student,
            reference="INV-W-001",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate(),
            total_amount=Decimal("50.00"),
            balance_amount=Decimal("50.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Fee",
            quantity=Decimal("1"),
            unit_price=Decimal("50.00"),
            amount=Decimal("50.00"),
        )

    def test_pay_invoice_with_wallet_creates_payment_and_debits_wallet(self):
        _wallet = ParentWallet.objects.create(
            school=self.school,
            user=self.user,
            balance=Decimal("100.00"),
            currency_code="XAF",
        )
        payment, updated_wallet = pay_invoice_with_wallet(
            school=self.school,
            user=self.user,
            invoice=self.invoice,
            amount=Decimal("50.00"),
        )
        self.assertEqual(payment.method, PaymentMethodCode.WALLET)
        self.assertEqual(payment.amount, Decimal("50.00"))
        self.assertEqual(updated_wallet.balance, Decimal("50.00"))
        txn = WalletTransaction.objects.get(payment=payment)
        self.assertEqual(txn.amount, Decimal("-50.00"))
        self.assertEqual(txn.kind, WalletTransaction.Kind.PAYMENT)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.computed_balance, Decimal("0.00"))

    def test_top_up_wallet_creates_positive_transaction_and_balance(self):
        wallet, txn = top_up_wallet(
            school=self.school,
            user=self.user,
            amount=Decimal("75.00"),
            reference="TOPUP-BATCH15",
        )
        self.assertEqual(wallet.balance, Decimal("75.00"))
        self.assertEqual(txn.kind, WalletTransaction.Kind.TOP_UP)
        self.assertEqual(txn.amount, Decimal("75.00"))
        self.assertEqual(txn.balance_after, Decimal("75.00"))
        self.assertEqual(txn.reference, "TOPUP-BATCH15")

    def test_pay_invoice_with_wallet_insufficient_balance_raises(self):
        ParentWallet.objects.create(
            school=self.school,
            user=self.user,
            balance=Decimal("10.00"),
            currency_code="XAF",
        )
        with self.assertRaises(ValueError) as ctx:
            pay_invoice_with_wallet(
                school=self.school,
                user=self.user,
                invoice=self.invoice,
                amount=Decimal("50.00"),
            )
        self.assertIn("Insufficient", str(ctx.exception))

    def test_pay_invoice_with_wallet_partial_payment_reduces_balance(self):
        ParentWallet.objects.create(
            school=self.school,
            user=self.user,
            balance=Decimal("100.00"),
            currency_code="XAF",
        )
        payment, wallet = pay_invoice_with_wallet(
            school=self.school,
            user=self.user,
            invoice=self.invoice,
            amount=Decimal("30.00"),
        )
        self.assertEqual(payment.amount, Decimal("30.00"))
        self.assertEqual(wallet.balance, Decimal("70.00"))
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.computed_balance, Decimal("20.00"))

    def test_pay_invoice_with_wallet_amount_exceeds_invoice_balance_raises(self):
        ParentWallet.objects.create(
            school=self.school,
            user=self.user,
            balance=Decimal("200.00"),
            currency_code="XAF",
        )
        with self.assertRaises(ValueError) as ctx:
            pay_invoice_with_wallet(
                school=self.school,
                user=self.user,
                invoice=self.invoice,
                amount=Decimal("60.00"),
            )
        self.assertIn("exceeds", str(ctx.exception).lower())

    def test_pay_invoice_with_wallet_non_positive_amount_raises(self):
        ParentWallet.objects.create(
            school=self.school,
            user=self.user,
            balance=Decimal("100.00"),
            currency_code="XAF",
        )
        with self.assertRaises(ValueError) as ctx:
            pay_invoice_with_wallet(
                school=self.school,
                user=self.user,
                invoice=self.invoice,
                amount=Decimal("0"),
            )
        self.assertIn("positive", str(ctx.exception).lower())

    def test_pay_invoice_with_wallet_wrong_school_raises(self):
        other = School.objects.create(
            name="Other",
            slug="other-wallet-school",
            subdomain="other-wallet-school",
            is_active=True,
        )
        ParentWallet.objects.create(
            school=self.school,
            user=self.user,
            balance=Decimal("100.00"),
            currency_code="XAF",
        )
        with self.assertRaises(ValueError) as ctx:
            pay_invoice_with_wallet(
                school=other,
                user=self.user,
                invoice=self.invoice,
                amount=Decimal("10.00"),
            )
        self.assertIn("does not belong", str(ctx.exception).lower())
