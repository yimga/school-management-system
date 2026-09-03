"""Finance import → ledger closure tests (batch 1821)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase, override_settings

from apps.finance.models import Invoice, InvoiceLine, JournalEntry, Payment
from apps.finance.provisioning_seed import ensure_tenant_compliance_profile
from apps.migration_cloud.finance_ledger import (
    resolve_import_paid_amount,
    sync_imported_finance_row,
)
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.finance_lander import FinanceLander
from apps.people.models import StudentProfile
from apps.schools.models import School


def _ctx(school, dry_run=False) -> LanderContext:
    return LanderContext(
        school=school, schema_name="", bundle_id=None, artifact_id=None, dry_run=dry_run
    )


class FinanceLedgerClosureTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Ledger Import Co", slug="ledger-import", subdomain="ledger-import"
        )
        ensure_tenant_compliance_profile(self.school)
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Fee",
            last_name="Payer",
            admission_number="ADM-ledger-1",
        )

    def _row(self, **overrides):
        row = {
            "student_external_id": "ADM-ledger-1",
            "reference": "INV-LEDGER-1",
            "amount": "1000.00",
            "due_date": "2025-09-30",
            "issue_date": "2025-09-01",
            "description": "Tuition term 1",
        }
        row.update(overrides)
        return row

    @override_settings(SEND_FINANCE_SIGNALS=True)
    def test_unpaid_import_issues_invoice_with_line_and_ledger(self):
        result = FinanceLander().land(
            canonical_rows=iter([self._row()]), ctx=_ctx(self.school)
        )
        self.assertEqual(result.quarantined, 0, result.errors)
        inv = Invoice.objects.get(reference="INV-LEDGER-1")
        self.assertEqual(inv.status, Invoice.Status.ISSUED)
        self.assertEqual(inv.total_amount, Decimal("1000.00"))
        self.assertEqual(InvoiceLine.objects.filter(invoice=inv).count(), 1)
        self.assertTrue(
            JournalEntry.objects.filter(source_type="invoice", source_id=inv.pk).exists()
        )
        self.assertFalse(Payment.objects.filter(invoice=inv).exists())

    @override_settings(SEND_FINANCE_SIGNALS=True)
    def test_partial_paid_import_creates_payment_and_partial_status(self):
        result = FinanceLander().land(
            canonical_rows=iter([self._row(paid_amount="400.00")]),
            ctx=_ctx(self.school),
        )
        self.assertEqual(result.quarantined, 0, result.errors)
        inv = Invoice.objects.get(reference="INV-LEDGER-1")
        self.assertEqual(inv.status, Invoice.Status.PARTIAL)
        self.assertEqual(inv.balance_amount, Decimal("600.00"))
        payment = Payment.objects.get(invoice=inv)
        self.assertEqual(payment.amount, Decimal("400.00"))
        self.assertEqual(payment.status, "completed")
        self.assertTrue(payment.external_reference.startswith("mc-import:"))
        self.assertTrue(
            JournalEntry.objects.filter(source_type="payment", source_id=payment.pk).exists()
        )

    @override_settings(SEND_FINANCE_SIGNALS=True)
    def test_balance_field_derives_paid_amount(self):
        row = self._row()
        self.assertEqual(
            resolve_import_paid_amount(row, Decimal("1000.00")),
            Decimal("0.00"),
        )
        self.assertEqual(
            resolve_import_paid_amount({"balance": "250.00"}, Decimal("1000.00")),
            Decimal("750.00"),
        )

    @override_settings(SEND_FINANCE_SIGNALS=True)
    def test_paid_import_is_idempotent_on_rerun(self):
        lander = FinanceLander()
        ctx = _ctx(self.school)
        lander.land(
            canonical_rows=iter([self._row(paid_amount="1000.00")]),
            ctx=ctx,
        )
        lander.land(
            canonical_rows=iter([self._row(paid_amount="1000.00")]),
            ctx=ctx,
        )
        inv = Invoice.objects.get(reference="INV-LEDGER-1")
        self.assertEqual(inv.status, Invoice.Status.PAID)
        self.assertEqual(Payment.objects.filter(invoice=inv).count(), 1)

    def test_sync_imported_finance_row_dry_run(self):
        profile = ensure_tenant_compliance_profile(self.school)
        inv = Invoice.objects.create(
            school=self.school,
            profile=profile,
            student=self.student,
            reference="DRY-1",
            total_amount=Decimal("500.00"),
            issued_date=date(2025, 9, 1),
        )
        outcome = sync_imported_finance_row(
            inv,
            self._row(reference="DRY-1", amount="500.00", paid_amount="100.00"),
            reference="DRY-1",
            school=self.school,
            dry_run=True,
        )
        self.assertTrue(outcome.get("dry_run"))
        self.assertFalse(Payment.objects.filter(invoice=inv).exists())

    def test_enrich_missing_required_maps_invoice_aliases(self):
        from apps.migration_cloud.landers._helpers import enrich_missing_required_row

        row = {
            "invoice_number": "INV-ENR-1",
            "total": "800.00",
            "admission_number": "ADM-ledger-1",
            "amount_paid": "200.00",
        }
        enriched, evidence = enrich_missing_required_row("finance", row, school=self.school)
        self.assertIn("reference←invoice_alias", evidence)
        self.assertEqual(enriched["reference"], "INV-ENR-1")
        self.assertEqual(enriched["amount"], "800.00")
        self.assertEqual(enriched["student_external_id"], "ADM-ledger-1")
        self.assertEqual(enriched["paid_amount"], "200.00")

    @override_settings(SEND_FINANCE_SIGNALS=True)
    def test_enriched_row_lands_via_lander(self):
        from apps.migration_cloud.landers._helpers import enrich_missing_required_row

        row = {
            "invoice_number": "INV-ENR-2",
            "total": "600.00",
            "admission_number": "ADM-ledger-1",
            "paid_amount": "600.00",
            "issue_date": "2025-09-01",
            "description": "Back fees",
        }
        result = FinanceLander().land(
            canonical_rows=iter([row]), ctx=_ctx(self.school)
        )
        self.assertEqual(result.quarantined, 0, result.errors)
        inv = Invoice.objects.get(reference="INV-ENR-2")
        self.assertEqual(inv.status, Invoice.Status.PAID)
