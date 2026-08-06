"""Tests for settlement reconciliation (M7).

PaymentReconciliation previously had a model + admin but ZERO creators — the
reconciliation surface was inert. These tests pin the producer and, critically,
include a MUST-FIRE assertion that a gateway payment booked ``completed``
without a settlement transaction id is flagged as a discrepancy. If the
discrepancy detection is ever silently removed, that test goes red.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.siteconfig.models import RegionConfig
from apps.accounts.models import User
from apps.finance.models import Payment, PaymentMethod, PaymentReconciliation
from apps.finance.reconciliation import (
    run_settlement_reconciliation,
    previous_calendar_month,
)

PERIOD_START = date(2026, 7, 1)
PERIOD_END = date(2026, 7, 31)


def _in_period():
    return timezone.make_aware(datetime(2026, 7, 15, 12, 0))


def _before_period():
    return timezone.make_aware(datetime(2026, 6, 15, 12, 0))


class SettlementReconciliationTests(TestCase):
    def setUp(self):
        uid = id(self)
        self.region, _ = RegionConfig.objects.get_or_create(
            code="RCN",
            defaults={
                "name": "Recon Region",
                "default_language": "en",
                "timezone": "UTC",
                "date_format": "DD/MM/YYYY",
            },
        )
        self.user = User.objects.create_user(
            "recon_%s" % uid, "recon_%s@test.com" % uid, "pass"
        )
        self.psp_method = PaymentMethod.objects.create(
            name="Stripe Card %s" % uid,
            method_type="card",
            gateway="stripe",
            region=self.region,
            created_by=self.user,
        )
        self.cash_method = PaymentMethod.objects.create(
            name="Cash Desk %s" % uid,
            method_type="check",
            gateway="manual",
            region=self.region,
            created_by=self.user,
        )

    def _payment(self, method, amount, *, status="completed", gtx=None,
                 refunded="0.00", fee="0.00", paid_at=None, ref=None):
        return Payment.objects.create(
            reference_number=ref or ("R%s" % id(object())),
            region=self.region,
            payment_method=method,
            amount=Decimal(str(amount)),
            refunded_amount=Decimal(str(refunded)),
            platform_fee=Decimal(str(fee)),
            currency_code="USD",
            purpose="tuition",
            status=status,
            gateway_transaction_id=gtx,
            paid_at=paid_at or _in_period(),
        )

    # ---- the model now has a producer at all -------------------------------

    def test_run_creates_reconciliation_row_previously_zero_creators(self):
        self.assertEqual(PaymentReconciliation.objects.count(), 0)
        self._payment(self.psp_method, "500.00", gtx="tx_ok_1")
        result = run_settlement_reconciliation(PERIOD_START, PERIOD_END)
        self.assertEqual(result["written"], 1)
        self.assertEqual(PaymentReconciliation.objects.count(), 1)

    def test_clean_gateway_payment_reconciles(self):
        self._payment(self.psp_method, "500.00", gtx="tx_ok_2")
        run_settlement_reconciliation(PERIOD_START, PERIOD_END)
        row = PaymentReconciliation.objects.get(payment_method=self.psp_method)
        self.assertEqual(row.status, "reconciled")
        self.assertEqual(row.total_payments, Decimal("500.00"))
        self.assertEqual(row.discrepancy_amount, Decimal("0.00"))
        self.assertIsNotNone(row.reconciled_at)

    # ---- MUST FIRE: unsettled gateway collection is a discrepancy ----------

    def test_gateway_payment_without_settlement_id_is_discrepancy(self):
        # Booked completed via an external PSP, but no settlement token recorded.
        self._payment(self.psp_method, "300.00", gtx=None)
        run_settlement_reconciliation(PERIOD_START, PERIOD_END)
        row = PaymentReconciliation.objects.get(payment_method=self.psp_method)
        self.assertEqual(row.status, "discrepancy")
        self.assertEqual(row.discrepancy_amount, Decimal("300.00"))
        # A discrepancy row is left un-timestamped — it needs a human.
        self.assertIsNone(row.reconciled_at)
        self.assertIn("settlement transaction id", row.discrepancy_notes)

    def test_cash_payment_without_token_is_not_a_discrepancy(self):
        # Manual/cash rail: no PSP settlement id is expected, so no discrepancy.
        self._payment(self.cash_method, "200.00", gtx=None)
        run_settlement_reconciliation(PERIOD_START, PERIOD_END)
        row = PaymentReconciliation.objects.get(payment_method=self.cash_method)
        self.assertEqual(row.status, "reconciled")
        self.assertEqual(row.discrepancy_amount, Decimal("0.00"))

    # ---- totals arithmetic --------------------------------------------------

    def test_totals_and_net_amount(self):
        self._payment(self.psp_method, "1000.00", gtx="tx_a", refunded="100.00", fee="30.00")
        self._payment(self.psp_method, "500.00", gtx="tx_b", refunded="0.00", fee="15.00")
        run_settlement_reconciliation(PERIOD_START, PERIOD_END)
        row = PaymentReconciliation.objects.get(payment_method=self.psp_method)
        self.assertEqual(row.total_payments, Decimal("1500.00"))
        self.assertEqual(row.total_refunds, Decimal("100.00"))
        self.assertEqual(row.total_fees, Decimal("45.00"))
        # net = payments - refunds - fees
        self.assertEqual(row.net_amount, Decimal("1355.00"))

    # ---- boundaries + idempotency ------------------------------------------

    def test_payment_outside_period_excluded(self):
        self._payment(self.psp_method, "999.00", gtx="tx_old", paid_at=_before_period())
        result = run_settlement_reconciliation(PERIOD_START, PERIOD_END)
        self.assertEqual(result["written"], 0)
        self.assertEqual(PaymentReconciliation.objects.count(), 0)

    def test_pending_payment_excluded(self):
        self._payment(self.psp_method, "50.00", status="pending", gtx=None)
        result = run_settlement_reconciliation(PERIOD_START, PERIOD_END)
        self.assertEqual(result["written"], 0)

    def test_dry_run_writes_nothing(self):
        self._payment(self.psp_method, "500.00", gtx="tx_dry")
        result = run_settlement_reconciliation(PERIOD_START, PERIOD_END, dry_run=True)
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["written"], 0)
        self.assertEqual(len(result["rows"]), 1)  # still computed + reported
        self.assertEqual(PaymentReconciliation.objects.count(), 0)

    def test_idempotent_rerun_updates_single_row(self):
        p = self._payment(self.psp_method, "400.00", gtx=None)  # discrepancy
        run_settlement_reconciliation(PERIOD_START, PERIOD_END)
        self.assertEqual(PaymentReconciliation.objects.count(), 1)
        # Operator records the missing settlement id; re-run flips it to clean.
        p.gateway_transaction_id = "tx_now_present"
        p.save(update_fields=["gateway_transaction_id"])
        run_settlement_reconciliation(PERIOD_START, PERIOD_END)
        self.assertEqual(PaymentReconciliation.objects.count(), 1)  # updated, not duplicated
        row = PaymentReconciliation.objects.get(payment_method=self.psp_method)
        self.assertEqual(row.status, "reconciled")
        self.assertEqual(row.discrepancy_amount, Decimal("0.00"))

    def test_previous_calendar_month_helper(self):
        start, end = previous_calendar_month(date(2026, 8, 5))
        self.assertEqual(start, date(2026, 7, 1))
        self.assertEqual(end, date(2026, 7, 31))
        # January rolls back across the year boundary.
        start, end = previous_calendar_month(date(2026, 1, 10))
        self.assertEqual(start, date(2025, 12, 1))
        self.assertEqual(end, date(2025, 12, 31))
