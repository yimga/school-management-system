"""Teaching graph closure + enrollment SOT sync — 2026-09-03."""

from __future__ import annotations

import uuid

from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import Classroom, Department, Specialty, Subject, SubjectAssignment
from apps.evals.models import TeacherAssignment
from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.migration_cloud.enrollment_sync import sync_enrollment_from_student_profile
from apps.migration_cloud.landers.base import LanderContext
from apps.migration_cloud.landers.enrollment_lander import EnrollmentLander
from apps.migration_cloud.teaching_graph import ensure_teaching_graph_closure
from apps.people.models import Enrollment, StudentProfile, TeacherProfile
from apps.schools.models import School


def _school(tag: str, **kwargs) -> School:
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    defaults = {
        "name": f"School {slug}",
        "slug": slug,
        "subdomain": slug,
        "country_code": "CM",
    }
    defaults.update(kwargs)
    return School.objects.create(**defaults)


class EnrollmentSyncTests(TestCase):
    def test_enrollment_lander_opens_active_enrollment_row(self):
        school = _school("enroll-sot")
        from apps.academics.models import AcademicYear

        year = AcademicYear.objects.create(
            school=school, name="2025-2026", start_date="2025-09-01", end_date="2026-06-30"
        )
        dept = Department.objects.create(school=school, name="General", code="GEN")
        classroom = Classroom.objects.create(
            school=school, name="Form 2A", code="F2A", academic_year=year, department=dept
        )
        Specialty.objects.create(
            school=school, name="PLUMBING", code="PL", department=dept
        )
        StudentProfile.objects.create(
            school=school,
            first_name="Jean",
            last_name="Paul",
            student_code="STU-1",
            academic_year=year,
        )
        ctx = LanderContext(
            school=school,
            schema_name="public",
            bundle_id=1,
            artifact_id=1,
        )
        row = {
            "student_external_id": "STU-1",
            "section_code": "F2A",
            "academic_year": "2025-2026",
            "specialty": "PLUMBING",
            "enrollment_status": "active",
        }
        result = EnrollmentLander().land(canonical_rows=iter([row]), ctx=ctx)
        self.assertEqual(result.quarantined, 0)
        student = StudentProfile.objects.get(school=school, student_code="STU-1")
        self.assertEqual(student.classroom_id, classroom.pk)
        enrollment = student.current_enrollment
        self.assertIsNotNone(enrollment)
        self.assertEqual(enrollment.classroom_id, classroom.pk)

    def test_sync_helper_idempotent(self):
        school = _school("sync-idem")
        from apps.academics.models import AcademicYear

        year = AcademicYear.objects.create(
            school=school, name="2025-2026", start_date="2025-09-01", end_date="2026-06-30"
        )
        student = StudentProfile.objects.create(
            school=school,
            first_name="A",
            last_name="B",
            student_code="S-2",
            academic_year=year,
        )
        first = sync_enrollment_from_student_profile(student)
        second = sync_enrollment_from_student_profile(student)
        self.assertIsNotNone(first)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(
            Enrollment.objects.filter(student=student, status=Enrollment.Status.ACTIVE).count(),
            1,
        )


class TeachingGraphClosureTests(TestCase):
    def test_provisions_grid_and_links_teacher_when_unambiguous(self):
        school = _school(
            "graph",
            settings={"grading": {"curriculum_tracks": ["vocational_trade"]}},
        )
        from apps.academics.models import AcademicYear, Term

        year = AcademicYear.objects.create(
            school=school,
            name="2025-2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        Term.objects.create(
            school=school,
            academic_year=year,
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
        )
        dept = Department.objects.create(school=school, name="PL DEPT", code="PLD")
        classroom = Classroom.objects.create(
            school=school, name="Form 2A", code="F2A", academic_year=year, department=dept
        )
        specialty = Specialty.objects.create(
            school=school, name="PLUMBING", code="PL", department=dept
        )
        subject = Subject.objects.create(school=school, name="Mathematics", code="MATH")
        StudentProfile.objects.create(
            school=school,
            first_name="Stu",
            last_name="One",
            student_code="G-1",
            academic_year=year,
            classroom=classroom,
            specialty=specialty,
            is_active=True,
        )
        teacher_user = get_user_model().objects.create_user(
            username=f"teacher-{uuid.uuid4().hex[:8]}",
            password="test-pass",
        )
        teacher = TeacherProfile.objects.create(
            school=school,
            staff_id="T-100",
            user=teacher_user,
        )
        for key in ("teaching_subjects", "teaching_classrooms"):
            DynamicFieldDefinition.objects.create(
                school=school,
                entity_type="staff",
                field_key=key,
                label=key.replace("_", " ").title(),
                data_type="json",
            )
        DynamicFieldValue.objects.create(
            school=school,
            entity_type="staff",
            entity_id=str(teacher.pk),
            field_key="teaching_subjects",
            value_json={"v": "Mathematics"},
        )
        DynamicFieldValue.objects.create(
            school=school,
            entity_type="staff",
            entity_id=str(teacher.pk),
            field_key="teaching_classrooms",
            value_json={"v": "Form 2A"},
        )

        outcome = ensure_teaching_graph_closure(school)
        self.assertGreater(
            SubjectAssignment.objects.filter(
                school=school, classroom=classroom, subject=subject
            ).count(),
            0,
        )
        link_summary = outcome.get("teacher_links") or {}
        self.assertGreaterEqual(link_summary.get("teacher_assignments_created", 0), 1)
        self.assertTrue(
            TeacherAssignment.objects.filter(
                school=school, teacher=teacher, subject_assignment__subject=subject
            ).exists()
        )
