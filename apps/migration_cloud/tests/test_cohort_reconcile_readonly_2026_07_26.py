"""A cohort-scoped (drill-down) reconcile must be READ-ONLY.

``reconcile_bundle`` groups artifacts by domain and filters to
``cohort["domains"]``; its parity + drift notes then cover only that subset.
Before this fix the APPLIED->RECONCILED close-out AND the encrypted-source-blob
purge still fired on that partial verification, so a tenant/operator drilling
into one domain (POST {"cohort":{"domains":["grades"]}}) could seal the whole
bundle and purge the source for every domain the pass never re-queried — a
silent, irreversible destruction of the migration's proof + source.

These tests lock the fix: a full (un-scoped) reconcile seals; a cohort reconcile
reports but never seals, purges, or auto-rolls-back.
"""

from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.reconciliation import reconcile_bundle
from apps.schools.models import School


class CohortReconcileReadOnlyTests(TestCase):
    def _applied_bundle(self, key):
        school = School.objects.create(
            name=f"Recon {key}", slug=f"recon-{key}", subdomain=f"recon-{key}",
            is_active=True, country_code="CM",
        )
        return MigrationBundle.objects.create(
            label="cohort recon test",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key=f"cohort-recon-{key}",
            status=BundleStatus.APPLIED,
            school=school,
            mapping_summary={"apply_totals": {"created": 0, "updated": 0, "quarantined": 0}},
        )

    def test_full_reconcile_seals_the_bundle(self):
        # Baseline: an un-scoped reconcile of a clean APPLIED bundle closes out.
        b = self._applied_bundle("full")
        reconcile_bundle(bundle_id=b.pk)
        b.refresh_from_db()
        self.assertEqual(b.status, BundleStatus.RECONCILED)

    def test_cohort_reconcile_is_readonly_never_seals(self):
        b = self._applied_bundle("cohort")
        report = reconcile_bundle(bundle_id=b.pk, cohort={"domains": ["students"]})
        b.refresh_from_db()
        # Must NOT seal (and therefore must NOT purge the source blobs).
        self.assertEqual(b.status, BundleStatus.APPLIED)
        self.assertTrue(
            any("read-only" in str(n).lower() for n in report.notes),
            msg=f"expected a read-only note, got {report.notes!r}",
        )
