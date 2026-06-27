"""Real capture -> restore round-trip for tenant immutable DR snapshots.

These tests prove the v2.0 snapshot payload carries *restorable row data* (not
counts-only) and that ``restore_from_snapshot`` MATERIALIZES those rows into a
fresh target school — verifying the HMAC signature first and failing closed on
tamper.

Tagged ``requires_postgres`` + ``@tag("dr_snapshot_restore")`` and wired into
``.github/workflows/django-tests-postgres.yml`` so the round-trip runs against
the same Postgres engine production uses. The restore path is ORM-only and also
passes on SQLite, but Postgres is the contract-of-record per the project's
Postgres-test convention (mirrors
``apps/schoolops/tests/test_resource_booking.py``).
"""

from __future__ import annotations

import unittest
import uuid
from pathlib import Path

from django.db import connection
from django.test import TestCase, override_settings, tag

from apps.academics.models import AcademicYear, Classroom, Department, Term
from apps.lifecycle.tenant_dr_snapshot import (
    SNAPSHOT_SCHEMA_VERSION,
    capture_daily_snapshot,
    restore_from_snapshot,
    verify_signature,
)
from apps.people.models import StudentProfile
from apps.schools.models import School

requires_postgres = unittest.skipUnless(
    connection.vendor == "postgresql",
    "DR snapshot restore round-trip is contract-tested on PostgreSQL "
    "(matches the production engine; ORM path also runs on SQLite).",
)


@override_settings(SECRET_KEY="test-dr-restore-roundtrip-signing-key")
@tag("dr_snapshot_restore")
class DrSnapshotRestoreRoundTripBaseTests(TestCase):
    """Backend-agnostic round-trip assertions (run on every engine)."""

    def _seed_source_school(self):
        slug = f"src-{uuid.uuid4().hex[:10]}"
        school = School.objects.create(
            name="Source Academy",
            slug=slug,
            subdomain=slug,
        )
        year = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-07-15",
            is_active=True,
        )
        dept = Department.objects.create(
            school=school,
            name="Sciences",
            code=f"SCI-{uuid.uuid4().hex[:6]}",
        )
        Term.objects.create(
            school=school,
            academic_year=year,
            name="FIRST",
            position=1,
            start_date="2025-09-01",
            end_date="2025-12-20",
            is_active=True,
        )
        Classroom.objects.create(
            school=school,
            academic_year=year,
            department=dept,
            name="Form 1A",
            code=f"F1A-{uuid.uuid4().hex[:6]}",
        )
        StudentProfile.objects.create(
            school=school,
            first_name="Ada",
            last_name="Lovelace",
            student_code=f"STU-{uuid.uuid4().hex[:8]}",
            date_of_birth="2013-05-10",
        )
        return school

    def test_payload_carries_real_rows_not_just_counts(self):
        school = self._seed_source_school()
        meta = capture_daily_snapshot(school)
        # Snapshot blob is non-trivial now (real rows, not an all-zero counts blob).
        self.assertGreater(meta["byte_size"], 200)

        restored = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(school.pk),
            expected_sig=meta["signature_hex"],
            target_school=school,  # idempotent re-apply onto the same tenant
        )
        self.assertEqual(restored["schema_version"], SNAPSHOT_SCHEMA_VERSION)
        tables = restored["tables"]
        self.assertEqual(len(tables["academics.AcademicYear"]), 1)
        self.assertEqual(len(tables["academics.Term"]), 1)
        self.assertEqual(len(tables["academics.Classroom"]), 1)
        self.assertEqual(len(tables["people.StudentProfile"]), 1)
        # The student row carries real field data, not a count.
        student_fields = tables["people.StudentProfile"][0]["fields"]
        self.assertEqual(student_fields["first_name"], "Ada")
        self.assertEqual(student_fields["last_name"], "Lovelace")

    def test_restore_materializes_rows_into_fresh_target(self):
        source = self._seed_source_school()
        src_year = AcademicYear.objects.get(school=source)
        src_classroom = Classroom.objects.get(school=source)
        src_student = StudentProfile.objects.get(school=source)

        meta = capture_daily_snapshot(source)

        # Fresh, EMPTY target tenant — the real self-host shape.
        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="Recovered Academy",
            slug=target_slug,
            subdomain=target_slug,
        )
        self.assertEqual(AcademicYear.objects.filter(school=target).count(), 0)
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 0)

        result = restore_from_snapshot(
            Path(meta["primary_uri"]),
            school_id=str(source.pk),
            expected_sig=meta["signature_hex"],
            target_school=target,
        )

        # Rows now EXIST under the target school (materialized, not counted).
        self.assertEqual(AcademicYear.objects.filter(school=target).count(), 1)
        self.assertEqual(Department.objects.filter(school=target).count(), 1)
        self.assertEqual(Term.objects.filter(school=target).count(), 1)
        self.assertEqual(Classroom.objects.filter(school=target).count(), 1)
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 1)

        # Field-level fidelity: values match the source, with fresh pks.
        tgt_year = AcademicYear.objects.get(school=target)
        self.assertEqual(tgt_year.name, src_year.name)
        self.assertEqual(str(tgt_year.start_date), str(src_year.start_date))
        self.assertNotEqual(tgt_year.pk, src_year.pk)

        tgt_student = StudentProfile.objects.get(school=target)
        self.assertEqual(tgt_student.first_name, src_student.first_name)
        self.assertEqual(tgt_student.last_name, src_student.last_name)
        self.assertEqual(tgt_student.student_code, src_student.student_code)
        # Out-of-scope FK is deliberately cleared on restore.
        self.assertIsNone(tgt_student.user_id)

        # Intra-snapshot FK was remapped to the freshly restored parent.
        tgt_classroom = Classroom.objects.get(school=target)
        self.assertEqual(tgt_classroom.academic_year_id, tgt_year.pk)
        self.assertNotEqual(tgt_classroom.pk, src_classroom.pk)

        # Restore report is honest about what it created.
        rep = result["restored"]["tables"]
        self.assertEqual(rep["academics.AcademicYear"]["created"], 1)
        self.assertEqual(rep["people.StudentProfile"]["created"], 1)

    def test_restore_is_idempotent(self):
        source = self._seed_source_school()
        meta = capture_daily_snapshot(source)
        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="Recovered Twice", slug=target_slug, subdomain=target_slug
        )
        kwargs = dict(
            school_id=str(source.pk),
            expected_sig=meta["signature_hex"],
            target_school=target,
        )
        restore_from_snapshot(Path(meta["primary_uri"]), **kwargs)
        # Second apply must not duplicate rows.
        second = restore_from_snapshot(Path(meta["primary_uri"]), **kwargs)
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 1)
        self.assertEqual(AcademicYear.objects.filter(school=target).count(), 1)
        self.assertEqual(
            second["restored"]["tables"]["people.StudentProfile"]["updated"], 1
        )
        self.assertEqual(
            second["restored"]["tables"]["people.StudentProfile"]["created"], 0
        )

    def test_tampered_blob_fails_closed_before_any_write(self):
        source = self._seed_source_school()
        meta = capture_daily_snapshot(source)
        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="No Recovery", slug=target_slug, subdomain=target_slug
        )

        # Flip one byte in the on-disk blob -> signature must no longer verify.
        path = Path(meta["primary_uri"])
        data = bytearray(path.read_bytes())
        data[-1] ^= 0xFF
        path.write_bytes(bytes(data))
        self.assertFalse(
            verify_signature(bytes(data), meta["signature_hex"], school_id=str(source.pk))
        )

        with self.assertRaises(ValueError):
            restore_from_snapshot(
                path,
                school_id=str(source.pk),
                expected_sig=meta["signature_hex"],
                target_school=target,
            )
        # Fail-closed: NOTHING was materialized into the target.
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 0)
        self.assertEqual(AcademicYear.objects.filter(school=target).count(), 0)

    def test_wrong_key_signature_fails_closed(self):
        source = self._seed_source_school()
        meta = capture_daily_snapshot(source)
        target_slug = f"tgt-{uuid.uuid4().hex[:10]}"
        target = School.objects.create(
            name="Wrong Key", slug=target_slug, subdomain=target_slug
        )
        with self.assertRaises(ValueError):
            restore_from_snapshot(
                Path(meta["primary_uri"]),
                school_id=str(source.pk),
                expected_sig="00" * 32,  # not the real signature
                target_school=target,
            )
        self.assertEqual(StudentProfile.objects.filter(school=target).count(), 0)


@requires_postgres
@tag("dr_snapshot_restore")
class DrSnapshotRestoreRoundTripPostgresTests(DrSnapshotRestoreRoundTripBaseTests):
    """Same round-trip, pinned to the production PostgreSQL engine."""
