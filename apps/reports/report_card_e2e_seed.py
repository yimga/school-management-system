"""Idempotent report-card publish + hash ledger seed for tenant Playwright E2E."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any
from unittest import mock

from django.db import transaction

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.evals.models import Evaluation, GradeApprovalRequest
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.registries.models import CountryRegistry
from apps.reports.models import ReportCard, ReportDocumentHash, TermPublishStatus
from apps.reports.views import _record_report_hash
from apps.schools.demo_user_seeding import resolve_demo_school, seed_demo_users_for_school
from apps.schools.models import School

_MOCK_PDF = b"%PDF-1.4 report-card-e2e-seed-mock"
_FIXTURE_REL = Path("var") / "e2e_report_card_fixture.json"


def _ensure_site_flags() -> None:
    site = get_platform_site_settings_record(create=True)
    site.apply_feature_control_state(
        field_updates={
            "enable_parent_portal": True,
            "enable_reports_pdf": True,
            "report_downloads_enabled": True,
            "grade_approval_enabled": True,
            "reports_require_approved_grades_before_publish": True,
            "reports_use_approved_grades_only": True,
            "backend_feature_flags": {
                "block_report_download_if_outstanding_balance": False,
            },
        },
    )


def seed_report_card_e2e_for_school(
    school: School,
    *,
    username_prefix: str = "demo",
    password: str = "Test1234",
    fixture_path: Path | None = None,
) -> dict[str, Any]:
    """Publish term results for the demo student; return fixture dict."""
    CountryRegistry.objects.get_or_create(code="CM", defaults={"name": "Cameroon"})
    _ensure_site_flags()

    pfx = (username_prefix or "demo").strip().lower()
    staff = User.objects.filter(username=f"{pfx}.admin", is_active=True).first()
    parent = User.objects.filter(username=f"{pfx}.parent", is_active=True).first()
    teacher_user = User.objects.filter(username=f"{pfx}.teacher", is_active=True).first()
    if not staff or not parent or not teacher_user:
        raise ValueError(
            f"Demo users missing for school={school.slug!r}; run seed_demo_tenant_users first."
        )

    year = (
        AcademicYear.objects.filter(school=school, is_active=True).first()
        or AcademicYear.objects.filter(school=school).order_by("-id").first()
    )
    if not year:
        year = AcademicYear.objects.create(
            school=school,
            name="2024-2025",
            start_date=date(2024, 9, 1),
            end_date=date(2025, 6, 30),
            is_active=True,
        )

    term = (
        Term.objects.filter(school=school, academic_year=year, is_active=True).first()
        or Term.objects.filter(school=school, academic_year=year).order_by("position").first()
    )
    if not term:
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="First",
            start_date=date(2024, 9, 1),
            end_date=date(2024, 12, 15),
            position=1,
            is_active=True,
        )

    student = StudentProfile.objects.filter(school=school).order_by("id").first()
    if not student:
        raise ValueError(f"No student profile for school={school.slug!r}")

    StudentGuardian.objects.update_or_create(
        guardian_user=parent,
        student=student,
        defaults={
            "relationship": StudentGuardian.Relationship.GUARDIAN,
            "can_view_results": True,
        },
    )

    department, _ = Department.objects.get_or_create(
        school=school, code="SCI-E2E", defaults={"name": "Science E2E"}
    )
    specialty, _ = Specialty.objects.get_or_create(
        school=school,
        department=department,
        code="PHY-E2E",
        defaults={"name": "Physics E2E"},
    )
    if student.specialty_id != specialty.id:
        student.specialty = specialty
        student.save(update_fields=["specialty"])
    if not student.classroom_id:
        classroom, _ = Classroom.objects.get_or_create(
            school=school,
            academic_year=year,
            code="SS1A-E2E",
            defaults={
                "department": department,
                "name": "SS1A E2E",
            },
        )
        student.classroom = classroom
        student.save(update_fields=["classroom"])
    classroom = student.classroom

    subject, _ = Subject.objects.get_or_create(
        school=school, name="Mathematics E2E"
    )
    subject_assignment, _ = SubjectAssignment.objects.get_or_create(
        school=school,
        academic_year=year,
        term=term,
        classroom=classroom,
        specialty=specialty,
        subject=subject,
        defaults={"coefficient": 1},
    )

    teacher = TeacherProfile.objects.filter(school=school, user=teacher_user).first()
    if not teacher:
        teacher = TeacherProfile.objects.create(school=school, user=teacher_user)

    Evaluation.objects.update_or_create(
        school=school,
        academic_year=year,
        term=term,
        subject_assignment=subject_assignment,
        student=student,
        defaults={
            "teacher": teacher,
            "seq1_score": 14,
            "seq2_score": 15,
            "exam_score": 16,
            "remarks": "E2E seed term",
        },
    )

    GradeApprovalRequest.objects.update_or_create(
        teacher=teacher,
        academic_year=year,
        term=term,
        subject_assignment=subject_assignment,
        defaults={
            "entries": [
                {
                    "student_id": student.id,
                    "scores": {"seq1": "14", "seq2": "15", "exam": "16"},
                }
            ],
            "summary": {"total_students": 1, "submitted_rows": 1},
            "status": GradeApprovalRequest.Status.APPROVED,
            "requested_by": teacher_user,
        },
    )

    with transaction.atomic():
        TermPublishStatus.objects.update_or_create(
            academic_year=year,
            term=term,
            classroom=None,
            defaults={"is_published": True, "published_by": staff},
        )

        rc, _ = ReportCard.objects.get_or_create(
            school=school,
            academic_year=year,
            term=term,
            student=student,
            type=ReportCard.Type.TERM,
        )

        with mock.patch("apps.reports.views.render_pdf_bytes", return_value=_MOCK_PDF):
            _record_report_hash(staff, rc, _MOCK_PDF)

    hash_row = ReportDocumentHash.objects.get(school=school, report_card=rc)
    from apps.reports.services import term_report_context

    grade_label = ""
    rows = term_report_context(student, year, term).get("rows") or []
    if rows:
        grade_label = str(rows[0].get("grade_label") or "")

    fixture = {
        "school_slug": school.slug,
        "student_id": student.id,
        "sha256_hash": hash_row.sha256_hash,
        "grade_label": grade_label,
        "subject_name": subject.name,
        "parent_username": f"{pfx}.parent",
        "staff_username": f"{pfx}.admin",
    }

    out = fixture_path or (_FIXTURE_REL)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    return fixture


def seed_report_card_e2e(
    *,
    school_slug: str = "",
    username_prefix: str = "demo",
    password: str = "Test1234",
    fixture_path: Path | None = None,
    stdout: Any = None,
    style: Any = None,
) -> dict[str, Any]:
    school = resolve_demo_school(school_slug=school_slug, extra_filter=None)
    if not school:
        raise ValueError("No active school found for report-card E2E seed.")

    if stdout is not None and style is not None:
        seed_demo_users_for_school(
            school,
            password=password,
            username_prefix=username_prefix,
            stdout=stdout,
            style=style,
        )

    fixture = seed_report_card_e2e_for_school(
        school,
        username_prefix=username_prefix,
        password=password,
        fixture_path=fixture_path,
    )
    if stdout is not None and style is not None:
        stdout.write(
            style.SUCCESS(
                f"OK report-card E2E — student_id={fixture['student_id']} "
                f"hash={fixture['sha256_hash'][:12]}…"
            )
        )
    return fixture
