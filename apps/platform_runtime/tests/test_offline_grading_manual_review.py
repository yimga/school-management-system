"""SODP depth — grading apply path honors manual_review conflict policy."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

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
from apps.evals.models import Evaluation
from apps.people.models import StudentProfile, TeacherProfile
from apps.platform_runtime.offline_queue import _apply_grading
from apps.schools.models import School, SchoolMembership


class OfflineGradingConflictPolicyTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"GradeConflict {uid}",
            slug=f"gc-{uid}",
            subdomain=f"gc{uid}",
            is_active=True,
        )
        self.teacher_user = User.objects.create_user(
            username=f"tgc_{uid}",
            password="pass-test",
            role=User.Role.TEACHER,
        )
        SchoolMembership.objects.get_or_create(
            user=self.teacher_user,
            school=self.school,
            defaults={"role": self.teacher_user.role, "is_primary": True},
        )
        self.year = AcademicYear.objects.create(
            name="Y",
            start_date="2025-01-01",
            end_date="2025-12-31",
            school=self.school,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="T1",
            position=1,
            start_date="2025-01-01",
            end_date="2025-06-30",
            is_active=True,
        )
        dept = Department.objects.create(name="Core", code=f"C{uid}", school=self.school)
        self.classroom = Classroom.objects.create(
            name="1A",
            academic_year=self.year,
            department=dept,
            school=self.school,
        )
        self.spec = Specialty.objects.create(
            school=self.school,
            department=dept,
            name="General",
            code=f"G{uid}",
        )
        self.subject = Subject.objects.create(school=self.school, name="Algebra")
        self.student = StudentProfile.objects.create(
            first_name="Stu",
            last_name="Dent",
            classroom=self.classroom,
            school=self.school,
            specialty=self.spec,
            academic_year=self.year,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            school=self.school,
        )
        self.assignment = SubjectAssignment.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.spec,
            subject=self.subject,
        )

    def test_conflicts_when_server_evaluation_differs(self):
        Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("12.00"),
            seq2_score=Decimal("11.00"),
            exam_score=Decimal("10.00"),
        )
        result = _apply_grading(
            self.school.pk,
            self.teacher_user.pk,
            {
                "subject_assignment_id": self.assignment.pk,
                "student_id": self.student.pk,
                "academic_year_id": self.year.pk,
                "term_id": self.term.pk,
                "seq1_score": 15,
                "seq2_score": 11,
                "exam_score": 10,
            },
        )
        self.assertFalse(result.get("ok"))
        self.assertTrue(result.get("conflict"))
        self.assertEqual(result.get("details", {}).get("policy"), "manual_review")

    def test_dedups_when_server_evaluation_matches(self):
        Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.assignment,
            student=self.student,
            teacher=self.teacher,
            seq1_score=Decimal("12.00"),
        )
        result = _apply_grading(
            self.school.pk,
            self.teacher_user.pk,
            {
                "subject_assignment_id": self.assignment.pk,
                "student_id": self.student.pk,
                "academic_year_id": self.year.pk,
                "term_id": self.term.pk,
                "seq1_score": 12,
            },
        )
        self.assertTrue(result.get("ok"))
        self.assertTrue(result.get("dedup"))
