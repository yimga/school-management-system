"""M26 — GATEWAY and WALLET settlements are producers of the fractional ledger.

The fractional clearance sub-ledger + its consumers were live
(``reports.services.student_has_financial_clearance`` on report cards,
``academics.year_close`` on re-enrollment), and the CASH_COUNTER producer was
wired (``payment_orchestration.reconcile_offline_payment_intent``) — but
``FractionalPaymentLedger.Source.GATEWAY`` and ``.WALLET`` had NO producer in
product code. So a parent who paid school fees via M-Pesa / Paystack /
Flutterwave / MTN MoMo (gateway webhook) or from the cashless wallet, in
instalments, never got a clearance row => ``enrollment_clearance_for_invoice()``
stayed False => they were blocked from report cards AND year-close
re-enrollment permanently, even though the platform explicitly intends the
opposite (pay enough irregular instalments -> see results / re-enroll).

These tests drive the REAL production entry points — ``record_provider_payment``
(the webhook's sole Payment producer) and ``pay_invoice_with_wallet`` (behind
both the parent-portal and API wallet-pay views) — so they fail if either
producer is ever unwired. They also pin the money-path safety contract: a
redelivered gateway webhook (this repo HAD a redelivery-500 storm) must NOT
double-credit clearance, and the row must carry the TENANT's currency (XAF),
never the blind USD default.
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    InvoiceLine,
    ParentWallet,
    PaymentMethodCode,
)
from apps.finance.models_fractional_ledger import FractionalPaymentLedger
from apps.finance.services import pay_invoice_with_wallet, record_provider_payment
from apps.people.models import StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.reports.services import student_has_financial_clearance
from apps.schools.models import School

User = get_user_model()


class _FractionalProducerBase(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Rail School",
            slug="rail-prod",
            subdomain="rail-prod",
            is_active=True,
        )
        # Cameroon / XAF: proves the row carries the TENANT's currency (resolved
        # from the invoice by the producer), not the hardcoded USD default.
        self.profile = ComplianceProfile.objects.create(
            name="Rail", country_code="CM", currency_code="XAF"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Kofi",
            last_name="Owusu",
            student_code="STU-RAIL-1",
            academic_year=self.year,
            is_active=True,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            student=self.student,
            academic_year=self.year,
            reference="INV-RAIL-001",
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            issued_date=timezone.localdate(),
            due_date=timezone.localdate(),
            total_amount=Decimal("1000.00"),
            balance_amount=Decimal("1000.00"),
        )
        InvoiceLine.objects.create(
            invoice=self.invoice,
            description="Tuition",
            quantity=Decimal("1"),
            unit_price=Decimal("1000.00"),
            amount=Decimal("1000.00"),
        )
        # Gate ON (flag defaults True; explicit for the end-to-end assertions).
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={
                "backend_feature_flags": {
                    "block_report_download_if_outstanding_balance": True,
                },
            },
        )


class GatewaySettlementFeedsFractionalLedgerTests(_FractionalProducerBase):
    def test_gateway_settlement_posts_a_fractional_row_in_tenant_currency(self):
        self.assertEqual(
            FractionalPaymentLedger.objects.filter(invoice=self.invoice).count(), 0
        )

        payment = record_provider_payment(
            invoice=self.invoice,
            amount="600.00",
            method=PaymentMethodCode.MTN_MOMO,
            reference="MPESA-REF-600",
            external_reference="MPESA-TXN-600-A",
        )
        self.assertIsNotNone(payment)

        rows = FractionalPaymentLedger.objects.filter(invoice=self.invoice)
        self.assertEqual(
            rows.count(), 1, "a confirmed gateway settlement must feed the sub-ledger"
        )
        row = rows.first()
        self.assertEqual(row.amount, Decimal("600.00"))
        self.assertEqual(row.school_id, self.school.pk)
        self.assertEqual(row.source, FractionalPaymentLedger.Source.GATEWAY)
        # Tenant currency, never the blind "USD" default.
        self.assertEqual(row.currency_code, "XAF")
        self.assertTrue(row.enrollment_clearance_met, "600/1000 clears the 50% bar")
        self.assertEqual(row.idempotency_key, f"gateway-payment-{payment.pk}")

    def test_gateway_partial_payer_report_card_unblocks_end_to_end(self):
        # M-Pesa payer is blocked from their report card before any settlement.
        self.assertFalse(student_has_financial_clearance(self.student, self.year))

        record_provider_payment(
            invoice=self.invoice,
            amount="600.00",
            method=PaymentMethodCode.MTN_MOMO,
            reference="MPESA-REF-600",
            external_reference="MPESA-TXN-600-B",
        )

        # Invoice is still not fully paid — clearance comes from the sub-ledger.
        self.invoice.refresh_from_db()
        self.assertGreater(self.invoice.computed_balance, Decimal("0.00"))
        self.assertTrue(
            student_has_financial_clearance(self.student, self.year),
            "paying 60% via M-Pesa must unblock results (micro-finance loop)",
        )

    def test_redelivered_gateway_webhook_does_not_double_post(self):
        # A gateway webhook can redeliver (this repo HAD a redelivery-500 storm).
        # The same external_reference resolves to the SAME Payment row, so the
        # producer must be a no-op the second time — never double-credit.
        p1 = record_provider_payment(
            invoice=self.invoice,
            amount="600.00",
            method=PaymentMethodCode.MTN_MOMO,
            reference="MPESA-REF-600",
            external_reference="MPESA-TXN-DUP",
        )
        p2 = record_provider_payment(
            invoice=self.invoice,
            amount="600.00",
            method=PaymentMethodCode.MTN_MOMO,
            reference="MPESA-REF-600",
            external_reference="MPESA-TXN-DUP",
        )
        self.assertEqual(p1.pk, p2.pk, "redelivery must update the same Payment row")

        rows = FractionalPaymentLedger.objects.filter(invoice=self.invoice)
        self.assertEqual(
            rows.count(), 1, "redelivered webhook must not double-post clearance"
        )

    def test_below_threshold_gateway_payment_still_blocks(self):
        record_provider_payment(
            invoice=self.invoice,
            amount="200.00",
            method=PaymentMethodCode.MTN_MOMO,
            reference="MPESA-REF-200",
            external_reference="MPESA-TXN-200",
        )
        row = FractionalPaymentLedger.objects.get(invoice=self.invoice)
        self.assertFalse(
            row.enrollment_clearance_met, "200/1000 is below the 50% bar"
        )
        self.assertFalse(student_has_financial_clearance(self.student, self.year))


class WalletSettlementFeedsFractionalLedgerTests(_FractionalProducerBase):
    def setUp(self):
        super().setUp()
        self.parent = User.objects.create_user(
            username="parent_rail",
            email="parent_rail@example.com",
            password="pw",
            role=User.Role.PARENT,
        )
        self.wallet = ParentWallet.objects.create(
            school=self.school,
            user=self.parent,
            balance=Decimal("1000.00"),
            currency_code="XAF",
        )

    def test_wallet_settlement_posts_a_fractional_row(self):
        self.assertEqual(
            FractionalPaymentLedger.objects.filter(invoice=self.invoice).count(), 0
        )

        payment, _wallet = pay_invoice_with_wallet(
            school=self.school,
            user=self.parent,
            invoice=self.invoice,
            amount=Decimal("600.00"),
        )

        rows = FractionalPaymentLedger.objects.filter(invoice=self.invoice)
        self.assertEqual(
            rows.count(), 1, "a wallet debit must feed the sub-ledger"
        )
        row = rows.first()
        self.assertEqual(row.amount, Decimal("600.00"))
        self.assertEqual(row.school_id, self.school.pk)
        self.assertEqual(row.source, FractionalPaymentLedger.Source.WALLET)
        self.assertEqual(row.currency_code, "XAF")
        self.assertTrue(row.enrollment_clearance_met, "600/1000 clears the 50% bar")
        self.assertEqual(row.idempotency_key, f"wallet-payment-{payment.pk}")

    def test_wallet_partial_payer_unblocks_end_to_end(self):
        self.assertFalse(student_has_financial_clearance(self.student, self.year))

        pay_invoice_with_wallet(
            school=self.school,
            user=self.parent,
            invoice=self.invoice,
            amount=Decimal("600.00"),
        )

        self.invoice.refresh_from_db()
        self.assertGreater(self.invoice.computed_balance, Decimal("0.00"))
        self.assertTrue(
            student_has_financial_clearance(self.student, self.year),
            "paying 60% from the wallet must unblock results",
        )

    def test_two_wallet_instalments_post_two_rows_and_cumulatively_clear(self):
        # Two distinct wallet pays mint two distinct Payments => two distinct
        # clearance rows whose cumulative total crosses the threshold. This is
        # NOT double-posting: each is a real separate instalment.
        pay_invoice_with_wallet(
            school=self.school,
            user=self.parent,
            invoice=self.invoice,
            amount=Decimal("300.00"),
        )
        self.assertFalse(student_has_financial_clearance(self.student, self.year))

        pay_invoice_with_wallet(
            school=self.school,
            user=self.parent,
            invoice=self.invoice,
            amount=Decimal("300.00"),
        )

        rows = FractionalPaymentLedger.objects.filter(invoice=self.invoice)
        self.assertEqual(rows.count(), 2)
        self.assertTrue(student_has_financial_clearance(self.student, self.year))
