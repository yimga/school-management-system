from datetime import date

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
from apps.reports.services import annual_report_context, term_report_context
from apps.platform_runtime.helpers import get_platform_site_settings_record


class CameroonReportContextTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 1),
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="FIRST",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 5),
            position=1,
            is_active=True,
        )
        department = Department.objects.create(name="Science", code="SCI")
        specialty = Specialty.objects.create(
            department=department, name="General", code="GEN"
        )
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=department,
            name="Form 3A",
            code="F3A",
        )
        self.subject = Subject.objects.create(name="Mathematics")
        self.subject_assignment = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.classroom,
            specialty=specialty,
            subject=self.subject,
            coefficient=2,
        )
        teacher_user = User.objects.create_user(
            username="teacher_ctx", password="pass123", role=User.Role.TEACHER
        )
        self.teacher = TeacherProfile.objects.create(user=teacher_user)
        self.student_a = StudentProfile.objects.create(
            first_name="Ada",
            last_name="A",
            student_code="CTX001",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=specialty,
            is_active=True,
        )
        self.student_b = StudentProfile.objects.create(
            first_name="Ben",
            last_name="B",
            student_code="CTX002",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=specialty,
            is_active=True,
        )

        Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            student=self.student_a,
            teacher=self.teacher,
            seq1_score=16,
            seq2_score=15,
            exam_score=17,
        )
        Evaluation.objects.create(
            academic_year=self.year,
            term=self.term,
            subject_assignment=self.subject_assignment,
            student=self.student_b,
            teacher=self.teacher,
            seq1_score=10,
            seq2_score=11,
            exam_score=12,
        )

        site = get_platform_site_settings_record(create=True)
        site.reports_use_approved_grades_only = False
        site.save(update_fields=["reports_use_approved_grades_only"])

    def test_term_context_exposes_bilingual_labels_and_sequence_cues(self):
        context = term_report_context(self.student_a, self.year, self.term)

        self.assertIn("labels", context)
        self.assertEqual(context["labels"]["average"], "Average / Moyenne")
        self.assertIn("sequence_cues", context)
        self.assertTrue(any(item["key"] == "seq1" for item in context["sequence_cues"]))
        self.assertIn("class_rank_display", context["summary"])
        self.assertIn(" / ", context["summary"]["class_rank_display"])
        self.assertIn("best_average", context["summary"])
        self.assertIn("worst_average", context["summary"])
        self.assertIn("class_average", context["summary"])
        self.assertTrue(context["rows"])
        first_row = context["rows"][0]
        self.assertIn("subject_rank_display", first_row)
        self.assertIn(" / ", first_row["subject_rank_display"])
        self.assertIn("teacher_name", first_row)

    def test_annual_context_provides_consistent_rank_display(self):
        context = annual_report_context(self.student_a, self.year)

        self.assertIn("class_rank_display", context)
        self.assertIn("school_rank_display", context)
        self.assertIn(" / ", context["class_rank_display"])
        self.assertIn(" / ", context["school_rank_display"])
        if context["term_rows"]:
            self.assertIn("rank_display", context["term_rows"][0])
            self.assertIn(" / ", context["term_rows"][0]["rank_display"])
