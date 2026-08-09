"""Seal: a real reconcile writes migration status back so the readiness phase resolves.

build_school_readiness reads the public-onboarding migration status from
School.settings, which the Migration Cloud pipeline never wrote back — so a
school that opted into a vendor migration saw the "Data migrated" phase pending
forever even after the bundle RECONCILED. The reconcile now marks it completed.

These tests FAIL before reconciliation writes the status back.
"""
from __future__ import annotations

from django.test import TestCase

from apps.migration_cloud.models import BundleStatus, IntakeMethod, MigrationBundle
from apps.migration_cloud.reconciliation import _mark_onboarding_migration_completed
from apps.schools.models import School
from apps.schools.school_readiness import build_school_readiness


def _migrate_phase(result):
    return next((p for p in result["phases"] if p.get("key") == "migrate"), None)


class ReconcileWritesBackMigrationStatusTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Reconcile Writeback",
            slug="reconcile-wb",
            subdomain="reconcile-wb",
            is_active=True,
            country_code="CM",
            settings={
                "rmc_public_onboarding": {
                    "migration": {"vendor_slug": "powerschool", "status": "in_progress"}
                }
            },
        )
        self.bundle = MigrationBundle.objects.create(
            label="rc",
            intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="rc-wb-1",
            status=BundleStatus.RECONCILED,
            school=self.school,
        )

    def _fresh(self):
        return School.objects.get(pk=self.school.pk)

    def test_migrate_phase_pending_before_writeback(self):
        phase = _migrate_phase(build_school_readiness(self._fresh()))
        self.assertIsNotNone(phase)
        self.assertFalse(phase["done"])

    def test_writeback_marks_completed_and_resolves_phase(self):
        _mark_onboarding_migration_completed(self.bundle)
        s = self._fresh()
        self.assertEqual(
            s.settings["rmc_public_onboarding"]["migration"]["status"], "completed"
        )
        phase = _migrate_phase(build_school_readiness(s))
        self.assertTrue(phase["done"])

    def test_writeback_with_no_school_is_safe(self):
        self.bundle.school = None
        # Must not raise.
        _mark_onboarding_migration_completed(self.bundle)
