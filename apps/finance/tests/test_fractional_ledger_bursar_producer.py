"""M26 — the bursar's offline-intent approval is the fractional ledger's PRODUCER.

The fractional sub-ledger + its enrollment-clearance gate were fully built and the
CONSUMER side was live (``reports.services.student_has_financial_clearance``, wired
into the report-card/transcript views + year-close), but nothing in production ever
called ``post_partial_payment`` — it was reachable only from its own unit tests.

So in production the sub-ledger was permanently EMPTY =>
``enrollment_clearance_for_invoice()`` could never return True => a student who paid
a partial instalment over the counter stayed blocked from their report card forever,
even though reports.services explicitly intends the opposite ("an invoice that has
met the tenant enrollment-clearance threshold no longer blocks results"). The
headline micro-finance loop (pay enough irregular instalments -> see results) was
dead on arrival.

These tests drive the REAL bursar path (``reconcile_offline_payment_intent``, the
single entry point behind both the single- and bulk-approve queue views) rather than
calling the service directly, so they fail if the producer is ever unwired again.

They also pin the currency: ``Invoice`` has no ``currency_code`` field (only the
optional canonical ``currency`` FK), so the ledger's old
``getattr(invoice, "currency_code", None) or "USD"`` silently stamped EVERY row USD.
A CM/XAF tenant must get XAF.
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
    OfflinePaymentIntent,
)
from apps.finance.models_fractional_ledger import FractionalPaymentLedger
from apps.finance.payment_orchestration import reconcile_offline_payment_intent
from apps.people.models import StudentProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.reports.services import student_has_financial_clearance
from apps.schools.models import School


class BursarApprovalFeedsFractionalLedgerTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Bursar School",
            slug="bursar-prod",
            subdomain="bursar-prod",
            is_active=True,
        )
        # Cameroon / XAF: proves the row carries the TENANT's currency, not the
        # hardcoded USD the old getattr(invoice, "currency_code") fell through to.
        self.profile = ComplianceProfile.objects.create(
            name="Bursar", country_code="CM", currency_code="XAF"
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ama",
            last_name="Mensah",
            student_code="STU-BURSAR-1",
            academic_year=self.year,
            is_active=True,
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            school=self.school,
            student=self.student,
            academic_year=self.year,
            reference="INV-BURSAR-001",
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
        self.bursar = get_user_model().objects.create_user(
            username="bursar_m26", password="pw"
        )
        # Gate ON (flag defaults True; explicit for the test).
        site = get_platform_site_settings_record(create=True)
        site.apply_feature_control_state(
            field_updates={
                "backend_feature_flags": {
                    "block_report_download_if_outstanding_balance": True,
                },
            },
        )

    def _queued_intent(self, amount: str) -> OfflinePaymentIntent:
        return OfflinePaymentIntent.objects.create(
            invoice=self.invoice,
            recorded_by=self.bursar,
            amount=Decimal(amount),
            payment_method="CASH",
            status=OfflinePaymentIntent.Status.QUEUED_REVIEW,
        )

    def test_bursar_approval_posts_a_fractional_row_in_tenant_currency(self):
        intent = self._queued_intent("600.00")
        self.assertEqual(
            FractionalPaymentLedger.objects.filter(invoice=self.invoice).count(), 0
        )

        reconcile_offline_payment_intent(intent, reconciled_by=self.bursar)

        rows = FractionalPaymentLedger.objects.filter(invoice=self.invoice)
        self.assertEqual(rows.count(), 1, "bursar approval must feed the sub-ledger")
        row = rows.first()
        self.assertEqual(row.amount, Decimal("600.00"))
        self.assertEqual(row.school_id, self.school.pk)
        self.assertEqual(row.source, FractionalPaymentLedger.Source.CASH_COUNTER)
        # The bug this pins: NOT the blind "USD" default.
        self.assertEqual(row.currency_code, "XAF")
        self.assertTrue(row.enrollment_clearance_met, "600/1000 clears the 50% bar")

    def test_partial_payer_report_card_unblocks_end_to_end(self):
        # Before any counter payment the student is blocked from their report card.
        self.assertFalse(student_has_financial_clearance(self.student, self.year))

        reconcile_offline_payment_intent(
            self._queued_intent("600.00"), reconciled_by=self.bursar
        )

        # The regular Payment ledger is reconciled but the invoice is still not
        # fully paid — clearance comes from the fractional sub-ledger.
        self.invoice.refresh_from_db()
        self.assertGreater(self.invoice.computed_balance, Decimal("0.00"))
        self.assertTrue(
            student_has_financial_clearance(self.student, self.year),
            "paying 60% over the counter must unblock results (micro-finance loop)",
        )

    def test_below_threshold_counter_payment_still_blocks(self):
        reconcile_offline_payment_intent(
            self._queued_intent("200.00"), reconciled_by=self.bursar
        )
        row = FractionalPaymentLedger.objects.get(invoice=self.invoice)
        self.assertFalse(row.enrollment_clearance_met, "200/1000 is below the 50% bar")
        self.assertFalse(student_has_financial_clearance(self.student, self.year))

    def test_approval_is_idempotent_and_cannot_double_post(self):
        intent = self._queued_intent("600.00")
        reconcile_offline_payment_intent(intent, reconciled_by=self.bursar)

        # A second reconcile of the same intent is refused outright, so the
        # sub-ledger can never be double-credited from one cash receipt.
        with self.assertRaises(ValueError):
            reconcile_offline_payment_intent(intent, reconciled_by=self.bursar)

        rows = FractionalPaymentLedger.objects.filter(invoice=self.invoice)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().idempotency_key, f"offline-intent-{intent.pk}")
