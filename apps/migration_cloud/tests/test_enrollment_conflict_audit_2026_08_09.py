"""Seal: the enrollment lander must audit overwrites, not silently last-writer-win.

The enrollment lander did a bare ``setattr`` on an existing StudentProfile and
appended ``{"pk": …, "old": {}}`` -- so (a) it logged NO ``MigrationConflict``,
meaning an operator's PRESERVE decision was never consulted, and (b) the
field-level apply audit (which reads ``entry["old"].keys()``) NEVER recorded the
enrollment overwrites -- exactly the mutations that touch pre-existing student
records. Every other person lander routes existing-row writes through
``detect_conflict`` + ``conflict_resolution_for``.

These tests FAIL against the bare-setattr code and PASS against the fix.
"""

from __future__ import annotations

from datetime import date

from django.test import TestCase
from django.utils import timezone

from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.enrollment_lander import EnrollmentLander
from apps.migration_cloud.models import (
    BundleStatus,
    ConflictResolution,
    IntakeMethod,
    MigrationBundle,
    MigrationConflict,
)
from apps.people.models import StudentProfile
from apps.schools.models import School

_CANONICAL_MODEL = f"{StudentProfile.__module__}.{StudentProfile.__name__}"


class EnrollmentConflictAuditTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Enr Seal", slug="enr-seal", subdomain="enr-seal",
            is_active=True, country_code="CM",
        )
        self.bundle = MigrationBundle.objects.create(
            label="enr", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="enr-1", status=BundleStatus.MAPPED, school=self.school,
        )
        self.student = StudentProfile.objects.create(
            school=self.school, student_code="PS-1", admission_number="PS-1",
            first_name="Ada", last_name="Lovelace", date_of_birth=date(2010, 5, 1),
            status=StudentProfile.Status.ALUMNI,
        )
        self.lander = EnrollmentLander()

    def _land(self, rows):
        ctx = LanderContext(
            school=self.school, bundle_id=self.bundle.pk, artifact_id=1,
            dry_run=False, schema_name="",
        )
        return self.lander.land(canonical_rows=iter(rows), ctx=ctx)

    def test_overwrite_logs_conflict_and_snapshots_old(self):
        # enrollment_status active -> RETURNING is a genuine overwrite of ALUMNI.
        res = self._land([{"student_external_id": "PS-1", "enrollment_status": "active"}])
        self.student.refresh_from_db()
        self.assertEqual(self.student.status, StudentProfile.Status.RETURNING)

        # (a) The overwritten field name is now recorded in `old` (was {}).
        self.assertTrue(res.updated_ids_with_old_values)
        old = res.updated_ids_with_old_values[0]["old"]
        self.assertEqual(old.get("status"), StudentProfile.Status.ALUMNI)

        # (b) A MigrationConflict is logged for operator review (none before).
        conflicts = MigrationConflict.objects.filter(
            bundle=self.bundle, domain="enrollment",
        )
        self.assertEqual(conflicts.count(), 1)
        self.assertIn("status", conflicts.first().changed_fields)

    def test_preserve_resolution_skips_overwrite(self):
        # Operator resolved this row as PRESERVE before re-running apply.
        MigrationConflict.objects.create(
            bundle=self.bundle, domain="enrollment",
            canonical_model=_CANONICAL_MODEL, canonical_pk=str(self.student.pk),
            legacy_id="PS-1", existing_values={"status": "ALUMNI"},
            incoming_values={"status": "RETURNING"}, changed_fields=["status"],
            resolution=ConflictResolution.PRESERVE, resolved_at=timezone.now(),
        )
        res = self._land([{"student_external_id": "PS-1", "enrollment_status": "active"}])
        self.student.refresh_from_db()
        # PRESERVE honored: the status is NOT overwritten, counted as skipped.
        self.assertEqual(self.student.status, StudentProfile.Status.ALUMNI)
        self.assertGreaterEqual(res.skipped, 1)
