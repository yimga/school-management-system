"""Phase 1: processor referral revenue-share attribution.

These tests prove the PRODUCER actually fires on a real Payment save (this codebase's
recurring failure mode is scaffolding with no producer), the math is correct, the upsert
is idempotent, refunds void the accrual, and the reconciliation reader aggregates.
"""

from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.billing.models import ProcessorRevenueShareAccrual
from apps.billing.revenue_share import (
    resolve_processor_revshare_percent,
    summarize_processor_revenue_share,
)
from apps.finance.models import Payment, PaymentMethod
from apps.schools.models import School
from apps.siteconfig.models_platform_catalog import RegionConfig


@override_settings(SEND_FINANCE_SIGNALS=True)
class ProcessorRevenueShareAttributionTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Attribution School",
            slug="attribution-school",
            subdomain="attribution-school",
            is_active=True,
        )

    def _payment(self, **kw):
        defaults = dict(
            school=self.school,
            amount=Decimal("100.00"),
            status="completed",
            method="MTN_MOMO",
            currency_code="KES",
            paid_at=timezone.now(),
        )
        defaults.update(kw)
        return Payment.objects.create(**defaults)

    def test_completed_payment_creates_accrual_at_zero_default_rate(self):
        payment = self._payment()
        accrual = ProcessorRevenueShareAccrual.objects.get(
            source_payment_id=payment.pk, school=self.school
        )
        self.assertEqual(accrual.gross_amount, Decimal("100.00"))
        self.assertEqual(accrual.currency_code, "KES")
        # No gateway on the payment => processor falls back to the (lowercased) rail code.
        self.assertEqual(accrual.processor_code, "mtn_momo")
        self.assertEqual(accrual.method_code, "MTN_MOMO")
        self.assertEqual(accrual.rev_share_percent, Decimal("0.000"))
        # No partner rate configured => no rebate fabricated, but GMV still recorded.
        self.assertEqual(accrual.rebate_amount, Decimal("0.00"))
        self.assertEqual(accrual.status, ProcessorRevenueShareAccrual.Status.ACCRUED)
        self.assertEqual(accrual.school_ref, "attribution-school")

    @override_settings(PLATFORM_PROCESSOR_REVSHARE_PERCENT="0.5")
    def test_rebate_computed_at_configured_rate(self):
        payment = self._payment(amount=Decimal("200.00"))
        accrual = ProcessorRevenueShareAccrual.objects.get(
            source_payment_id=payment.pk, school=self.school
        )
        self.assertEqual(accrual.rev_share_percent, Decimal("0.5"))
        # 200.00 * 0.5 / 100 = 1.00
        self.assertEqual(accrual.rebate_amount, Decimal("1.00"))

    @override_settings(
        PLATFORM_PROCESSOR_REVSHARE_PERCENT="0.5",
        PLATFORM_PROCESSOR_REVSHARE_PERCENT_BY_CODE={"flutterwave": "1.5"},
    )
    def test_per_processor_override_wins_over_default(self):
        self.assertEqual(resolve_processor_revshare_percent("flutterwave"), Decimal("1.5"))
        self.assertEqual(resolve_processor_revshare_percent("momo"), Decimal("0.5"))

    def test_pending_payment_creates_no_accrual(self):
        payment = self._payment(status="pending")
        self.assertFalse(
            ProcessorRevenueShareAccrual.objects.filter(
                source_payment_id=payment.pk
            ).exists()
        )

    def test_upsert_is_idempotent_across_resaves(self):
        payment = self._payment()
        payment.description = "touched once"
        payment.save()
        payment.save()
        self.assertEqual(
            ProcessorRevenueShareAccrual.objects.filter(
                source_payment_id=payment.pk, school=self.school
            ).count(),
            1,
        )

    def test_refund_voids_the_accrual(self):
        payment = self._payment()
        self.assertEqual(
            ProcessorRevenueShareAccrual.objects.get(
                source_payment_id=payment.pk, school=self.school
            ).status,
            ProcessorRevenueShareAccrual.Status.ACCRUED,
        )
        payment.status = "refunded"
        payment.save()
        accrual = ProcessorRevenueShareAccrual.objects.get(
            source_payment_id=payment.pk, school=self.school
        )
        self.assertEqual(accrual.status, ProcessorRevenueShareAccrual.Status.VOIDED)
        self.assertEqual(accrual.rebate_amount, Decimal("0.00"))

    def test_partial_refund_reduces_attributed_gmv(self):
        payment = self._payment(amount=Decimal("100.00"))
        payment.refunded_amount = Decimal("40.00")
        payment.save()  # still status=completed, net = 60.00
        accrual = ProcessorRevenueShareAccrual.objects.get(
            source_payment_id=payment.pk, school=self.school
        )
        self.assertEqual(accrual.gross_amount, Decimal("60.00"))

    @override_settings(PLATFORM_PROCESSOR_REVSHARE_PERCENT="1")
    def test_gateway_precedence_and_reconciliation_summary(self):
        region, _ = RegionConfig.objects.get_or_create(
            code="KEN",
            defaults={"name": "Kenya", "default_currency": "KES", "grading_scale": "0-100"},
        )
        pm = PaymentMethod.objects.create(
            name="Flutterwave KE",
            method_type="card",
            gateway="flutterwave",
            region=region,
        )
        payment = self._payment(
            amount=Decimal("300.00"), payment_method=pm, method="OTHER"
        )
        accrual = ProcessorRevenueShareAccrual.objects.get(
            source_payment_id=payment.pk, school=self.school
        )
        # The PaymentMethod gateway (the PSP that owes the rebate) wins over the rail code.
        self.assertEqual(accrual.processor_code, "flutterwave")
        self.assertEqual(accrual.rebate_amount, Decimal("3.00"))  # 300 * 1 / 100

        summary = summarize_processor_revenue_share()
        rows = {r["processor_code"]: r for r in summary["by_processor_currency"]}
        self.assertIn("flutterwave", rows)
        self.assertEqual(rows["flutterwave"]["gross"], Decimal("300.00"))
        self.assertEqual(rows["flutterwave"]["rebate"], Decimal("3.00"))
        self.assertEqual(summary["totals_by_currency"]["KES"]["rebate"], Decimal("3.00"))
