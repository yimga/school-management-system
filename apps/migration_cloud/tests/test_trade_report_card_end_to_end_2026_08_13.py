"""Increment (i) — the north star, for a TVET TRADE student, end to end.

Report-card readiness already proved a migrated student generates a report card
AFTER a teacher manually creates the subject assignment. Increment (g)'s
student-driven per-specialty grid now AUTO-BUILDS that assignment during the
migration itself: a roster-only TVET export (specialties + a student on a trade,
no subjects, no grid) comes out the other side with the country subject catalog,
a specialty↔subject curriculum, and assignments matching the student's
(classroom, specialty) — so the only remaining human step is entering a mark.

This proves the whole chain for a trade student: ingest → gap-fill → the trade
student is gradeable WITHOUT any manual assignment → a report card generates.
"""

from __future__ import annotations

import io
import types

from django.test import TestCase

from apps.migration_cloud import artifact_blob_store as store
from apps.migration_cloud.models import (
    ArtifactFormat,
    BundleStatus,
    IntakeMethod,
    MigrationArtifact,
    MigrationBundle,
)


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


def _add_artifact(bundle, filename, headers, rows, sha):
    data = _xlsx_bytes(headers, rows)
    art = MigrationArtifact.objects.create(
        bundle=bundle, path_within_bundle=filename, filename=filename,
        detected_format=ArtifactFormat.XLSX, byte_size=len(data), sha256=sha,
    )
    store.capture_artifact_blob(
        art, types.SimpleNamespace(content_opener=lambda d=data: io.BytesIO(d))
    )


class TradeStudentReportCardEndToEndTests(TestCase):
    def test_migrated_trade_student_grid_auto_built_and_report_generates(self):
        from apps.academics.models import SubjectAssignment, Term
        from apps.accounts.models import User
        from apps.evals.models import Evaluation
        from apps.migration_cloud.orchestrator import apply_bundle
        from apps.migration_cloud.pipeline import advance_bundle
        from apps.people.models import StudentProfile, TeacherProfile
        from apps.platform_runtime.helpers import get_platform_site_settings_record
        from apps.reports.bulk_generation import generate_term_report_cards
        from apps.reports.models import TermPublishStatus
        from apps.schools.models import School

        school = School.objects.create(
            name="TVET E2E", subdomain="tvet-e2e-trade", country_code="CM",
        )
        bundle = MigrationBundle.objects.create(
            label="e2e", intake_method=IntakeMethod.FILE_UPLOAD,
            idempotency_key="rc-trade-e2e", status=BundleStatus.INGESTING, school=school,
        )
        # A roster-only TVET export: a trade + a student on it. No subjects, no grid.
        _add_artifact(
            bundle, "specialties.xlsx", ["NAME", "CODE", "DEPARTMENT"],
            [["WELDING AND METAL FABRICATION - MWIP", "MWIP", "WELDING - MWIP"]], "a" * 64,
        )
        _add_artifact(
            bundle, "students.xlsx",
            ["ID", "Name", "Gender", "Date of Birth", "Class", "Specialty"],
            [["247", "ACHU DECLAN ANDOH", "Female", "2012-11-16", "Form Two",
              "WELDING AND METAL FABRICATION"]], "b" * 64,
        )
        advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
        apply_bundle(bundle_id=bundle.pk, workers=1)

        student = StudentProfile.objects.filter(school=school).first()
        self.assertIsNotNone(student)
        self.assertIsNotNone(student.classroom_id, "student placed (G7)")
        self.assertIsNotNone(student.specialty_id, "student on the WELDING trade")
        year = student.academic_year
        term = (
            Term.objects.filter(school=school, academic_year=year, is_active=True).first()
            or Term.objects.filter(school=school, academic_year=year).order_by("position").first()
        )
        self.assertIsNotNone(term)

        # THE NEW CAPABILITY (g): the per-specialty grid auto-built assignments for
        # the migrated trade student — no teacher had to create them.
        auto = SubjectAssignment.objects.filter(
            school=school, classroom=student.classroom,
            specialty=student.specialty, academic_year=year, term=term,
        )
        self.assertGreater(
            auto.count(), 0,
            "migration should auto-build the trade student's (classroom, specialty) grid",
        )

        # Enter a single mark on an AUTO-BUILT assignment (the only human step left).
        assignment = auto.first()
        teacher_user = User.objects.create_user(username="e2e.teacher", email="t@e2e.cm")
        if hasattr(teacher_user, "role"):
            teacher_user.role = User.Role.TEACHER
            teacher_user.save(update_fields=["role"])
        teacher = TeacherProfile.objects.create(school=school, user=teacher_user)
        Evaluation.objects.update_or_create(
            school=school, academic_year=year, term=term,
            subject_assignment=assignment, student=student,
            defaults={"teacher": teacher, "seq1_score": 14, "seq2_score": 15, "exam_score": 16},
        )

        site = get_platform_site_settings_record(create=True)  # config-resolver-allow: test singleton feature flags
        site.apply_feature_control_state(
            field_updates={
                "enable_reports_pdf": True,
                "report_downloads_enabled": True,
                "reports_require_approved_grades_before_publish": False,
                "reports_use_approved_grades_only": False,
                "backend_feature_flags": {"block_report_download_if_outstanding_balance": False},
            },
        )
        staff = User.objects.create_user(username="e2e.staff", email="s@e2e.cm")
        TermPublishStatus.objects.update_or_create(
            academic_year=year, term=term, classroom=None,
            defaults={"is_published": True, "published_by": staff},
        )

        result = generate_term_report_cards(
            school=school, academic_year=year, term=term,
            enforce_publish=True, enforce_fee_clearance=False, dry_run=True,
        )
        self.assertGreaterEqual(
            result.generated, 1,
            f"a migrated TRADE student should be report-card-ready with an auto-built "
            f"grid; skips={getattr(result, 'reasons', {})}",
        )
