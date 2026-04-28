"""North Star SLICE 1 — Rosetta grade normalization (service, API, UI wiring)."""

from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace

from django.test import TestCase
from django.urls import reverse

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
from apps.evals.models import AssessmentWeights, Evaluation, TeacherAssignment
from apps.evals.rosetta_stone import (
    convert_grade,
    format_rosetta_line,
    normalized_to_target_score,
    view_grade_in_target_system,
)
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


class RosettaStoneServiceTests(TestCase):
    def test_16_of_20_converts_to_percentage_80(self):
        out = convert_grade(16.0, "0-20", "0-100", school=None)
        self.assertAlmostEqual(out["converted_score"], 80.0, places=1)
        self.assertAlmostEqual(out["normalized_value"], 0.8, places=3)

    def test_normalized_value_maps_to_target_scale(self):
        self.assertEqual(normalized_to_target_score(Decimal("0.8"), "0-100"), Decimal("80.00"))

    def test_blank_grade_does_not_crash(self):
        ev = SimpleNamespace(
            final_score=None,
            normalized_value=None,
            school=None,
        )
        r = view_grade_in_target_system(ev, "0-100")
        self.assertFalse(r.get("ok"))
        self.assertEqual(r.get("reason"), "no_score")

    def test_invalid_scale_id_falls_back(self):
        out = convert_grade(10.0, "0-20", "not-a-scale", school=None)
        self.assertEqual(out["to_scale"], "0-20")

    def test_view_prefers_stored_normalized(self):
        ev = SimpleNamespace(
            final_score=Decimal("16"),
            normalized_value=Decimal("0.8000"),
            school=None,
        )
        r = view_grade_in_target_system(ev, "0-100", prefer_stored_normalization=True)
        self.assertTrue(r.get("ok"))
        self.assertTrue(r.get("used_stored_normalized"))
        self.assertAlmostEqual(r["converted_score"], 80.0, places=1)

    def test_format_rosetta_line_is_safe(self):
        self.assertEqual(format_rosetta_line(None, "0-100"), "—")
        self.assertIn(
            "%",
            format_rosetta_line(
                SimpleNamespace(
                    final_score=Decimal("10"),
                    normalized_value=Decimal("0.5"),
                    school=None,
                ),
                "0-100",
            ),
        )


class RosettaGradePreviewApiTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Rosetta Test School",
            slug="rosetta-test-school",
            subdomain="rosetta-test-sx",
            is_active=True,
            settings={"grading_scale": "0-20"},
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-08-31",
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name=Term.Name.FIRST,
            position=1,
            start_date="2025-09-01",
            end_date="2025-11-30",
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(
            department=dept, name="General", code="GEN"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year, department=dept, name="F1A", code="F1A"
        )
        self.subject = Subject.objects.create(name="Math")
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=self.specialty,
            subject=self.subject,
            coefficient=1.0,
        )
        self.teacher_user = User.objects.create_user(
            "rosetta-teacher", "t@ex.com", "pass", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(user=self.teacher_user)
        TeacherAssignment.objects.create(
            teacher=self.teacher,
            academic_year=self.year,
            subject_assignment=self.subject_assignment,
            is_active=True,
        )
        self.student = StudentProfile.objects.create(
            first_name="A",
            last_name="Student",
            student_code="RSET01",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
            is_active=True,
        )
        AssessmentWeights.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            seq1_weight=0,
            seq2_weight=0,
            exam_weight=100,
            mock_weight=0,
            practical_weight=0,
            score_scale=20,
        )
        self.evaluation = Evaluation.objects.create(
            school=self.school,
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            student=self.student,
            teacher=self.teacher,
            exam_score=Decimal("16.0"),
        )

    def test_teacher_can_fetch_rosetta_preview(self):
        self.client.login(username="rosetta-teacher", password="pass")
        url = reverse("evals:rosetta_grade_preview_api")
        r = self.client.get(
            url, {"evaluation_id": self.evaluation.id, "to_scale": "0-100"}
        )
        self.assertEqual(r.status_code, 200)
        data = json.loads(r.content.decode())
        self.assertTrue(data.get("ok"))
        self.assertAlmostEqual(data.get("converted_score", 0), 80.0, places=0)

    def test_other_user_forbidden(self):
        other = User.objects.create_user(
            "other", "o@ex.com", "pass", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(user=other)
        self.client.login(username="other", password="pass")
        url = reverse("evals:rosetta_grade_preview_api")
        r = self.client.get(url, {"evaluation_id": self.evaluation.id})
        self.assertEqual(r.status_code, 403)
