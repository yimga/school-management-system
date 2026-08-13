"""Report-card readiness after Migration Cloud ingest (Increment 1 + 2).

The north star: a migration hasn't "run a school" until that school can produce a
term report card. This proves the post-apply gap-fill scaffolds everything a report
card needs that is KNOWABLE from a bare export — a country-aware Term structure and
a country-aware grading scale — and then that the full downstream report-card chain
works end-to-end once a teacher assigns a subject and enters marks (the curriculum +
marks are the only pieces a bare export cannot carry).
"""

from __future__ import annotations

import io
import types

from django.test import TransactionTestCase

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


def _payload(data: bytes):
    return types.SimpleNamespace(content_opener=lambda: io.BytesIO(data))


def _add_artifact(bundle, path, filename, headers, rows, sha):
    data = _xlsx_bytes(headers, rows)
    art = MigrationArtifact.objects.create(
        bundle=bundle, path_within_bundle=path, filename=filename,
        detected_format=ArtifactFormat.XLSX, byte_size=len(data), sha256=sha,
    )
    store.capture_artifact_blob(art, _payload(data))


def _ingest_tvet_bundle(school, idem: str):
    bundle = MigrationBundle.objects.create(
        label="rc", intake_method=IntakeMethod.FILE_UPLOAD,
        idempotency_key=idem, status=BundleStatus.INGESTING, school=school,
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
    from apps.migration_cloud.orchestrator import apply_bundle
    from apps.migration_cloud.pipeline import advance_bundle

    advance_bundle(bundle_id=bundle.pk, use_accelerator=True)
    apply_bundle(bundle_id=bundle.pk, workers=1)
    return bundle


class ReportCardScaffoldTests(TransactionTestCase):
    def test_gap_fill_seeds_country_terms_and_grading_scale(self):
        from apps.academics.models import Term
        from apps.academics.structure_provisioning import _resolve_term_structure
        from apps.evals.models import GradingScale
        from apps.schools.models import School

        school = School.objects.create(
            name="TVET RC Scaffold", subdomain="tvet-rc-scaffold", country_code="CM",
        )
        _ingest_tvet_bundle(school, "rc-scaffold")

        # Terms: seeded to the school's country/region structure, exactly one active.
        year = school.academic_years.filter(is_active=True).first() or school.academic_years.first()
        self.assertIsNotNone(year)
        expected_count, _labels = _resolve_term_structure(school)
        terms = Term.objects.filter(school=school, academic_year=year)
        self.assertEqual(terms.count(), expected_count,
                         "terms should match the country/region structure")
        self.assertEqual(terms.filter(is_active=True).count(), 1,
                         "exactly one active term (marks entry 403s without one)")

        # Grading scale: a migrated school lands with a country-aware GradingScale.
        self.assertTrue(
            GradingScale.objects.filter(school=school).exists(),
            "gap-fill should seed a per-school grading scale",
        )


class ReportCardGeneratesAfterMigrationTests(TransactionTestCase):
    def test_report_card_generates_for_a_migrated_student(self):
        from apps.academics.models import Subject, SubjectAssignment, Term
        from apps.accounts.models import User
        from apps.evals.models import Evaluation
        from apps.people.models import StudentProfile, TeacherProfile
        from apps.platform_runtime.helpers import get_platform_site_settings_record
        from apps.reports.bulk_generation import generate_term_report_cards
        from apps.reports.models import TermPublishStatus
        from apps.schools.models import School

        school = School.objects.create(
            name="TVET RC Gen", subdomain="tvet-rc-gen", country_code="CM",
        )
        _ingest_tvet_bundle(school, "rc-gen")

        # The migration + gap-fill delivered: placement, year, terms, grading scale.
        student = StudentProfile.objects.filter(school=school).first()
        self.assertIsNotNone(student)
        self.assertIsNotNone(student.classroom_id, "student placed (G7)")
        self.assertIsNotNone(student.specialty_id, "student on their trade")
        year = student.academic_year
        self.assertIsNotNone(year, "student bound to the default year")
        term = (
            Term.objects.filter(school=school, academic_year=year, is_active=True).first()
            or Term.objects.filter(school=school, academic_year=year).order_by("position").first()
        )
        self.assertIsNotNone(term, "gap-fill seeded terms")

        # Report generation is gated by feature flags; enable the report path and
        # drop the approved-grades gate so a single seeded mark is enough.
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

        # The one step a bare export cannot carry: a teacher assigns a subject to
        # the student's (class, specialty) and enters a mark. Everything ELSE was
        # scaffolded by the migration.
        subject, _ = Subject.objects.get_or_create(school=school, name="Welding Practical")
        assignment, _ = SubjectAssignment.objects.get_or_create(
            school=school, academic_year=year, term=term,
            classroom=student.classroom, specialty=student.specialty, subject=subject,
            defaults={"coefficient": 4},
        )
        teacher_user = User.objects.create_user(username="rc.gen.teacher", email="t@rc.cm")
        if hasattr(teacher_user, "role"):
            teacher_user.role = User.Role.TEACHER
            teacher_user.save(update_fields=["role"])
        teacher = TeacherProfile.objects.create(school=school, user=teacher_user)
        Evaluation.objects.update_or_create(
            school=school, academic_year=year, term=term,
            subject_assignment=assignment, student=student,
            defaults={"teacher": teacher, "seq1_score": 14, "seq2_score": 15, "exam_score": 16},
        )

        staff = User.objects.create_user(username="rc.gen.staff", email="s@rc.cm")
        TermPublishStatus.objects.update_or_create(
            academic_year=year, term=term, classroom=None,
            defaults={"is_published": True, "published_by": staff},
        )

        # The proof: a report card is producible for the migrated student.
        result = generate_term_report_cards(
            school=school, academic_year=year, term=term,
            enforce_publish=True, enforce_fee_clearance=False, dry_run=True,
        )
        self.assertGreaterEqual(
            result.generated, 1,
            f"a migrated student should be report-card-ready; skips={getattr(result, 'reasons', {})}",
        )
