"""Student -> Specialty placement (G7).

A single-file TVET student roster carries the trade specialty INLINE
('WELDING AND METAL FABRICATION') while the specialties catalog row may carry
a trailing code ('WELDING AND METAL FABRICATION - MWIP'). These pin that the
student lander places the student on the matching Specialty (created in wave 0),
normalizing the trailing code so the two forms match, and preserves the raw
label when it cannot resolve — never quarantining an already-landed student.
"""

from __future__ import annotations

import io
import types

from django.test import TestCase, TransactionTestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.landers.student_lander import _norm_spec, _resolve_specialty_fuzzy
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)


class NormSpecTests(TestCase):
    def test_strips_trailing_code_and_folds(self):
        self.assertEqual(
            _norm_spec("WELDING AND METAL FABRICATION - MWIP"),
            "WELDING AND METAL FABRICATION",
        )
        self.assertEqual(_norm_spec("FASHION  DESIGN"), "FASHION DESIGN")
        self.assertEqual(_norm_spec("Accounting"), "ACCOUNTING")


class ResolveSpecialtyFuzzyTests(TestCase):
    def test_resolves_by_normalized_name(self):
        from apps.academics.models import Department, Specialty
        from apps.schools.models import School

        school = School.objects.create(name="R", subdomain="r-spec-fuzzy")
        dept = Department.objects.create(school=school, name="WELD", code="DPT-WELD-X")
        spec = Specialty.objects.create(
            school=school, department=dept,
            name="WELDING AND METAL FABRICATION - MWIP", code="SPC-MWIP-X",
        )
        # Inline roster label (no trailing code) resolves to the catalog row.
        self.assertEqual(
            _resolve_specialty_fuzzy(school, "WELDING AND METAL FABRICATION"), spec
        )
        # Exact name still works.
        self.assertEqual(
            _resolve_specialty_fuzzy(school, "WELDING AND METAL FABRICATION - MWIP"), spec
        )
        # A genuinely different trade does not wrong-link.
        self.assertIsNone(_resolve_specialty_fuzzy(school, "PLUMBING"))


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


class StudentSpecialtyEndToEndTests(TransactionTestCase):
    def test_student_placed_on_specialty(self):
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.migration_cloud.pipeline import advance_bundle
        from apps.people.models import StudentProfile
        from apps.schools.models import School

        school = School.objects.create(name="TVET Link", subdomain="tvet-link")
        bundle = MigrationBundle.objects.create(
            label="combo", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="student-spec-link", status=BundleStatus.INGESTING, school=school,
        )
        _add_artifact(
            bundle, "specialties.xlsx", "specialties.xlsx",
            ["NAME", "CODE", "DEPARTMENT"],
            [["WELDING AND METAL FABRICATION - MWIP", "MWIP", "WELDING - MWIP"],
             ["ACCOUNTING", "ACCOUNTX", "Accounting"]],
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

        student = StudentProfile.objects.filter(school=school).first()
        self.assertIsNotNone(student, "student should land")
        self.assertIsNotNone(student.specialty_id, "student should be placed on a specialty")
        self.assertEqual(student.specialty.name, "WELDING AND METAL FABRICATION - MWIP")
