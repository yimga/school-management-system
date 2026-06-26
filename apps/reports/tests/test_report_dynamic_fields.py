"""Report card dynamic EAV fields (Option C / metric 5)."""

from datetime import date

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department, Specialty, Term
from apps.metadata.models import DynamicFieldDefinition
from apps.metadata.services import set_dynamic_field_value
from apps.people.models import StudentProfile
from apps.reports.services import student_dynamic_fields_for_report, term_report_context
from apps.schools.models import School


class ReportCardDynamicFieldsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Dynamic Report School",
            slug="dynamic-report-school",
            subdomain="dynamic-report-school",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="First",
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            position=1,
            is_active=True,
        )
        department = Department.objects.create(
            school=self.school, name="General", code="GEN"
        )
        specialty = Specialty.objects.create(
            school=self.school, department=department, name="General", code="GEN"
        )
        classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=department,
            name="Form 1A",
            code="F1A",
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Ada",
            last_name="Lovelace",
            student_code="STU-DYN-001",
            classroom=classroom,
            specialty=specialty,
            academic_year=self.year,
            is_active=True,
        )
        DynamicFieldDefinition.objects.create(
            school=self.school,
            entity_type="people.studentprofile",
            field_key="blood_group",
            label="Blood group",
            data_type="string",
            is_active=True,
        )
        set_dynamic_field_value(
            self.student,
            "blood_group",
            "O+",
            school=self.school,
        )

    def test_student_dynamic_fields_for_report(self):
        rows = student_dynamic_fields_for_report(self.student, school=self.school)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["label"], "Blood group")
        self.assertEqual(rows[0]["value"], "O+")

    def test_term_report_context_includes_dynamic_fields(self):
        ctx = term_report_context(self.student, self.year, self.term)
        self.assertIn("student_dynamic_fields", ctx)
        self.assertEqual(ctx["student_dynamic_fields"][0]["value"], "O+")
