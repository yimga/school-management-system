"""Transfer Wave A — envelope → target-school bundle, dry-run end-to-end.

The Wave A exit criterion (design §7): a seeded student round-trips from the
source school into a target-school migration-cloud bundle in DRY-RUN with
correct preview counts — proving the internal-tenant intake rides the normal
pipeline (staging CSV → ingest → advance → dry-run apply) without a parallel
apply path. Real (non-dry-run) apply is Wave B.
"""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import AcademicYear, Attendance, Classroom, Department
from apps.interop.student_transfer_export import build_student_transfer_envelope
from apps.interop.transfer_apply import TransferApplyError
from apps.migration_cloud.models import BundleStatus, MigrationBundle
from apps.migration_cloud.transfer_intake import (
    TRANSFER_LABEL_PREFIX,
    TRANSFER_SOURCE_HINT,
    ingest_transfer_envelope,
)
from apps.people.models import StudentGuardian, StudentProfile
from apps.schools.models import School

User = get_user_model()

_DOMAINS = ("students", "guardians", "enrollment", "attendance")

# Force the orchestrator's inline (single-connection) apply path: the thread
# pool's fresh DB connections cannot see rows created inside this TestCase's
# transaction. mc_defaults.get honors this operator env override.
_WORKERS_ENV = {"MIGRATION_CLOUD__MIGRATION_CLOUD__ORCHESTRATOR__WORKER_COUNT": "1"}


@patch.dict("os.environ", _WORKERS_ENV)
class TransferIntakeDryRunTests(TestCase):
    def setUp(self):
        self.source = School.objects.create(
            name="Intake Source", slug="intake-src", subdomain="intake-src"
        )
        self.target = School.objects.create(
            name="Intake Target", slug="intake-tgt", subdomain="intake-tgt"
        )
        year = AcademicYear.objects.create(
            school=self.source,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
        )
        department = Department.objects.create(
            school=self.source, name="Science", code="SCI-IN"
        )
        classroom = Classroom.objects.create(
            school=self.source,
            academic_year=year,
            department=department,
            name="Form 3C",
            code="F3C-IN",
        )
        self.profile = StudentProfile.objects.create(
            school=self.source,
            first_name="Move",
            last_name="Able",
            student_code="IN-001",
            admission_number="ADM-IN-001",
            academic_year=year,
            classroom=classroom,
            joined_date=date(2025, 9, 2),
        )
        guardian_user = User.objects.create_user(
            username="intake_guardian",
            password="pass123",
            first_name="Care",
            last_name="Giver",
        )
        StudentGuardian.objects.create(
            guardian_user=guardian_user,
            student=self.profile,
            phone="+237600000002",
        )
        Attendance.objects.create(
            school=self.source,
            student=self.profile,
            classroom=classroom,
            date=date(2025, 10, 7),
        )
        self.envelope = build_student_transfer_envelope(
            self.profile, target_school=self.target, domains=_DOMAINS
        )

    def test_dry_run_end_to_end(self):
        result = ingest_transfer_envelope(
            self.envelope, target_school=self.target
        )
        self.assertEqual(result["bundle_status"], BundleStatus.MAPPED)
        self.assertTrue(result["apply"]["dry_run"])
        self.assertGreaterEqual(result["apply"]["total_created"], 1)

        bundle = MigrationBundle.objects.get(pk=result["bundle_id"])
        self.assertEqual(bundle.school_id, self.target.pk)
        self.assertEqual(bundle.source_hint, TRANSFER_SOURCE_HINT)
        self.assertTrue(bundle.label.startswith(TRANSFER_LABEL_PREFIX))
        self.assertEqual(bundle.artifacts.count(), len(_DOMAINS))
        self.assertIn("last_dry_run", bundle.size_summary)
        # Dry-run must write NO student rows at the target.
        self.assertFalse(
            StudentProfile.objects.filter(school=self.target).exists()
        )

    def test_reingest_same_envelope_reuses_bundle(self):
        first = ingest_transfer_envelope(self.envelope, target_school=self.target)
        second = ingest_transfer_envelope(self.envelope, target_school=self.target)
        self.assertEqual(first["bundle_id"], second["bundle_id"])
        bundle = MigrationBundle.objects.get(pk=first["bundle_id"])
        self.assertEqual(bundle.artifacts.count(), len(_DOMAINS))

    def test_wrong_target_school_refused(self):
        with self.assertRaises(TransferApplyError):
            ingest_transfer_envelope(self.envelope, target_school=self.source)

    def test_envelope_without_rows_refused(self):
        from apps.interop.transfer_envelope import build_student_envelope

        empty = build_student_envelope(
            source_tenant_id=str(self.source.pk),
            target_tenant_id=str(self.target.pk),
            canonical_data={},
        )
        with self.assertRaises(TransferApplyError):
            ingest_transfer_envelope(empty, target_school=self.target)
