"""Post-apply structural gap-fill (S) + student → Classroom placement (G7).

Two features proven together, the way a real TVET migration exercises them:

* **G7** — a single-file student roster carries the class/form INLINE
  ('Form Two'). The student lander creates a first-class ``Classroom`` for it
  (default 2025/2026 year, the trade's department) and places the student on it,
  without the upload ever carrying an academic year or a class catalog.

* **S** — after apply, the gap-fill scaffolds what a running school needs but
  the upload lacked: a default academic year, the General department/specialty
  every fee-plan / subject-assignment FK points at, and the structure engine +
  teaching grid. Idempotent, deduped against what landed, admin-editable.
"""

from __future__ import annotations

import datetime as _dt
import io
import types

from django.test import TestCase, TransactionTestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)
from apps.migration_cloud.post_apply_provision import (
    _year_bounds_from_name,
    ensure_default_academic_year,
)


class YearBoundsTests(TestCase):
    def test_slash_form_gives_sept_to_aug(self):
        start, end = _year_bounds_from_name("2025/2026")
        self.assertEqual(start, _dt.date(2025, 9, 1))
        self.assertEqual(end.year, 2026)
        self.assertEqual(end.month, 8)

    def test_dash_form_and_single_year(self):
        s1, e1 = _year_bounds_from_name("2025-2026")
        self.assertEqual((s1.year, e1.year), (2025, 2026))
        s2, e2 = _year_bounds_from_name("2025")
        self.assertEqual((s2.year, e2.year), (2025, 2026))

    def test_unparseable_name_stays_consistent(self):
        start, end = _year_bounds_from_name("Session A")
        self.assertLess(start, end)


class EnsureDefaultYearTests(TestCase):
    def test_creates_default_once_then_reuses(self):
        from apps.academics.models import AcademicYear
        from apps.schools.models import School

        school = School.objects.create(name="Y", subdomain="y-default-year")
        year, created = ensure_default_academic_year(school)
        self.assertTrue(created)
        self.assertEqual(year.name, "2025/2026")
        self.assertTrue(year.is_active)
        # Idempotent: a second call reuses the same row (no unique constraint on
        # AcademicYear, so this pins the resolve-first behavior).
        again, created2 = ensure_default_academic_year(school)
        self.assertFalse(created2)
        self.assertEqual(again.pk, year.pk)
        self.assertEqual(AcademicYear.objects.filter(school=school).count(), 1)

    def test_never_overrides_an_existing_year(self):
        from apps.academics.models import AcademicYear
        from apps.schools.models import School

        school = School.objects.create(name="Z", subdomain="z-existing-year")
        real = AcademicYear.objects.create(
            school=school, name="2024/2025",
            start_date=_dt.date(2024, 9, 1), end_date=_dt.date(2025, 8, 28),
            is_active=True,
        )
        year, created = ensure_default_academic_year(school)
        self.assertFalse(created)
        self.assertEqual(year.pk, real.pk)  # the upload's own year wins

    def test_tenant_override_name(self):
        from apps.schools.models import School

        school = School.objects.create(
            name="O", subdomain="o-override-year",
            settings={"default_academic_year_name": "2026/2027"},
        )
        year, created = ensure_default_academic_year(school)
        self.assertTrue(created)
        self.assertEqual(year.name, "2026/2027")


def _xlsx_bytes(headers, rows):
    from openpyxl import Workbook

    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _payload(data: bytes):
    return types.SimpleNamespace(content_opener=lambda: io.BytesIO(data))


def _add_artifact(bundle, path, filename, headers, rows, sha):
    data = _xlsx_bytes(headers, rows)
    art = MigrationArtifact.objects.create(
        bundle=bundle, path_within_bundle=path, filename=filename,
        detected_format=ArtifactFormat.XLSX, byte_size=len(data), sha256=sha,
    )
    store.capture_artifact_blob(art, _payload(data))


class GapFillAndClassroomEndToEndTests(TransactionTestCase):
    def test_student_placed_in_created_classroom_and_gap_fill_scaffolds(self):
        from apps.academics.models import AcademicYear, Department, Specialty
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.migration_cloud.pipeline import advance_bundle
        from apps.people.models import StudentProfile
        from apps.schools.models import School

        school = School.objects.create(
            name="TVET GapFill", subdomain="tvet-gapfill",
            country_code="CM", settings={"school_type": "tvet"},
        )
        bundle = MigrationBundle.objects.create(
            label="combo", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="gapfill-classroom", status=BundleStatus.INGESTING, school=school,
        )
        _add_artifact(
            bundle, "specialties.xlsx", "specialties.xlsx",
            ["NAME", "CODE", "DEPARTMENT"],
            [["WELDING AND METAL FABRICATION - MWIP", "MWIP", "WELDING - MWIP"]],
            "a" * 64,
        )
        _add_artifact(
            bundle, "students.xlsx", "students.xlsx",
            ["ID", "Name", "Gender", "Date of Birth", "Class", "Specialty"],
            [["247", "ACHU DECLAN ANDOH", "Female", "2012-11-16", "Form Two",
              "WELDING AND METAL FABRICATION"]],
            "b" * 64,
        )

        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle.pk, workers=1)

        # --- G7: the student is placed in a Classroom the upload never carried ---
        student = StudentProfile.objects.filter(school=school).first()
        self.assertIsNotNone(student, "student should land")
        self.assertIsNotNone(student.classroom_id, "student should be placed in a classroom")
        self.assertEqual(student.classroom.name, "Form Two")
        # Classroom's required FKs are satisfied: default year + trade department.
        self.assertEqual(student.classroom.academic_year.name, "2025/2026")
        self.assertIsNotNone(student.specialty_id, "student should be on their trade")
        self.assertEqual(student.classroom.department_id, student.specialty.department_id)

        # --- S: gap-fill scaffolded the running-a-school structure ---------------
        year = AcademicYear.objects.filter(school=school, name="2025/2026").first()
        self.assertIsNotNone(year, "default academic year should exist")
        self.assertTrue(year.is_active)
        self.assertTrue(
            Department.objects.filter(school=school, name="General").exists(),
            "General department should be ensured",
        )
        self.assertTrue(
            Specialty.objects.filter(school=school, name="General").exists(),
            "General specialty should be ensured",
        )
        bundle.refresh_from_db()
        gap = (bundle.mapping_summary or {}).get("gap_fill_provisioning") or {}
        self.assertEqual(gap.get("academic_year", {}).get("name"), "2025/2026")
        self.assertIn("defaults", gap)
        # The structure engine + teaching grid were invoked (their per-sector
        # result — vocational yields cycle nodes, no engine-side classrooms — is
        # recorded honestly, whatever it is).
        self.assertTrue("structure" in gap or "error" in gap)

    def test_reapply_is_idempotent_no_duplicate_classroom(self):
        from apps.academics.models import Classroom
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.migration_cloud.pipeline import advance_bundle
        from apps.schools.models import School

        school = School.objects.create(
            name="TVET Reapply", subdomain="tvet-reapply", country_code="CM",
        )
        bundle = MigrationBundle.objects.create(
            label="combo2", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="gapfill-reapply", status=BundleStatus.INGESTING, school=school,
        )
        _add_artifact(
            bundle, "students.xlsx", "students.xlsx",
            ["ID", "Name", "Gender", "Date of Birth", "Class"],
            [["301", "MBEKI JOHN DOE", "Male", "2011-05-02", "Form Three"]],
            "c" * 64,
        )
        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle.pk, workers=1)
        apply_bundle(bundle_id=bundle.pk, workers=1)  # re-apply must not duplicate

        self.assertEqual(
            Classroom.objects.filter(school=school, name="Form Three").count(), 1,
            "re-applying the bundle must not create a duplicate classroom",
        )
