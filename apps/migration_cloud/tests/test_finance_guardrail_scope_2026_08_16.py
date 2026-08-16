"""Finance guardrail #4 — import-delta scope + unverified-finance warn/require.

#4a: control totals compare against ONLY the invoices THIS bundle landed (via the
     id-mapping audit), so a school's pre-existing invoices never skew the totals and
     spuriously roll back a correct import.
#4b: finance that lands with NO expected_totals is never passed off silently — it is
     warned (recorded on the bundle) by default, and REFUSED when
     RMC_MIGRATION_REQUIRE_FINANCE_TOTALS is on.

Before the fix: #4a sees the whole-school total (pre-existing + imported); #4b returns
silently with no marker / no refusal.
"""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase, override_settings

from apps.migration_cloud import orchestrator
from apps.migration_cloud.guardrails import compute_observed_totals
from apps.migration_cloud.models import (
    BundleStatus,
    FinancialMismatchError,
    IntakeMethod,
    MigrationBundle,
    MigrationIdMapping,
)
from apps.migration_cloud.orchestrator import ArtifactApplyOutcome
from apps.schools.models import School


class _Base(TestCase):
    def _school(self, slug):
        return School.objects.create(
            name=f"School {slug}", slug=slug, subdomain=slug,
            is_active=True, is_approved=True, country_code="CM", settings={},
        )

    def _bundle(self, school, key, *, expected_totals=None):
        return MigrationBundle.objects.create(
            label=key, intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"guard-{key}", status=BundleStatus.APPLIED,
            school=school, expected_totals=expected_totals or {},
        )


class ImportDeltaScopeTests(_Base):
    def test_observed_totals_count_only_this_bundle(self):
        from apps.finance.models import Invoice
        from apps.finance.provisioning_seed import ensure_tenant_compliance_profile

        school = self._school("delta-scope")
        bundle = self._bundle(school, "delta")
        profile = ensure_tenant_compliance_profile(school)

        # A pre-existing invoice the school already had (NOT from any bundle)...
        Invoice.objects.create(profile=profile, total_amount=Decimal("500.00"), school=school)
        # ...and one this bundle landed, recorded in the id-mapping audit.
        mine = Invoice.objects.create(profile=profile, total_amount=Decimal("100.00"), school=school)
        MigrationIdMapping.objects.create(
            legacy_namespace="unknown_custom", legacy_id="INV-1",
            canonical_model="apps.finance.models.Invoice", school_id=school.id,
            domain="finance", bundle=bundle, canonical_pk=str(mine.pk),
        )

        totals = compute_observed_totals(bundle=bundle)
        # Scoped to the bundle: 100, NOT the whole-school 600. (Compare as Decimal —
        # SQLite/Postgres format the Sum differently, "100" vs "100.00".)
        self.assertEqual(Decimal(totals["finance.invoice_total_amount"]), Decimal("100.00"))
        self.assertEqual(totals["finance.invoice_count"], "1")

    def test_empty_scope_is_zero_not_whole_school(self):
        from apps.finance.models import Invoice
        from apps.finance.provisioning_seed import ensure_tenant_compliance_profile

        school = self._school("empty-scope")
        bundle = self._bundle(school, "empty")
        profile = ensure_tenant_compliance_profile(school)
        Invoice.objects.create(profile=profile, total_amount=Decimal("500.00"), school=school)
        # No id-mappings for this bundle -> observed is 0 (fails closed vs a non-zero expected).

        totals = compute_observed_totals(bundle=bundle)
        self.assertEqual(totals["finance.invoice_total_amount"], "0")
        self.assertEqual(totals["finance.invoice_count"], "0")


class UnverifiedFinanceTests(_Base):
    def _finance_outcome(self):
        return ArtifactApplyOutcome(
            artifact_id=1, path_within_bundle="fees.csv", domain="finance",
            migration_run_id=None, status="SUCCESS",
        )

    def test_warns_by_default_when_no_totals(self):
        school = self._school("warn")
        bundle = self._bundle(school, "warn", expected_totals={})
        orchestrator._maybe_check_financial_guardrail(bundle, [self._finance_outcome()])
        bundle.refresh_from_db()
        self.assertTrue(bundle.mapping_summary.get("finance_landed_unverified"))

    @override_settings(RMC_MIGRATION_REQUIRE_FINANCE_TOTALS=True)
    def test_refused_when_required_and_no_totals(self):
        school = self._school("require")
        bundle = self._bundle(school, "require", expected_totals={})
        with self.assertRaises(FinancialMismatchError):
            orchestrator._maybe_check_financial_guardrail(bundle, [self._finance_outcome()])

    def test_no_finance_no_warning(self):
        school = self._school("nofin")
        bundle = self._bundle(school, "nofin", expected_totals={})
        students = ArtifactApplyOutcome(
            artifact_id=1, path_within_bundle="students.csv", domain="students",
            migration_run_id=None, status="SUCCESS",
        )
        orchestrator._maybe_check_financial_guardrail(bundle, [students])
        bundle.refresh_from_db()
        self.assertNotIn("finance_landed_unverified", bundle.mapping_summary or {})
