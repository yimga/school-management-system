"""Wave E — state-reporting CSV exporter."""

from __future__ import annotations

import csv
import io
import uuid

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile
from apps.reports.state_reporting import (
    available_jurisdictions,
    build_state_report_rows,
    export_state_report_csv,
)
from apps.schools.models import School


class StateReportingTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"SR {uid}", slug=f"sr-{uid}", subdomain=f"sr{uid}", is_active=True
        )
        year = AcademicYear.objects.create(
            name="Y1", start_date="2025-01-01", end_date="2025-12-31", school=self.school
        )
        dept = Department.objects.create(name="D", code=f"D{uid}", school=self.school)
        classroom = Classroom.objects.create(
            academic_year=year, department=dept, name="C1", code=f"C{uid}", school=self.school
        )
        self.student = StudentProfile.objects.create(
            first_name="Nadia",
            last_name="Bello",
            date_of_birth="2014-02-20",
            gender="female",
            student_code=f"SSID{uid}",
            joined_date="2025-09-01",
            school=self.school,
            classroom=classroom,
        )

    def test_jurisdictions_available(self):
        js = available_jurisdictions()
        self.assertIn("GENERIC", js)
        self.assertIn("US_EDFACTS", js)
        self.assertIn("CA_CALPADS", js)

    def test_generic_rows_shape(self):
        rows = build_state_report_rows(self.school.id, "GENERIC")
        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["StudentID"], self.student.student_code)
        self.assertEqual(row["LastName"], "Bello")
        self.assertEqual(row["DateOfBirth"], "2014-02-20")

    def test_calpads_gender_code_single_letter(self):
        rows = build_state_report_rows(self.school.id, "CA_CALPADS")
        self.assertEqual(rows[0]["StudentGenderCode"], "F")  # 'female' -> 'F'
        self.assertEqual(rows[0]["SSID"], self.student.student_code)

    def test_csv_export_parses(self):
        text = export_state_report_csv(self.school.id, "US_EDFACTS")
        reader = list(csv.DictReader(io.StringIO(text)))
        self.assertEqual(len(reader), 1)
        self.assertEqual(reader[0]["StudentUniqueId"], self.student.student_code)
        self.assertIn("BirthDate", reader[0])

    def test_unknown_jurisdiction_falls_back_to_generic(self):
        rows = build_state_report_rows(self.school.id, "NOPE")
        self.assertIn("StudentID", rows[0])  # GENERIC shape
