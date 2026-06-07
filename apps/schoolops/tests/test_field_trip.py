"""Wave D — field-trip consent + offline medical checklist."""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department
from apps.compliance.models import ConsentRequest
from apps.people.models import StudentProfile
from apps.schoolops.field_trip import (
    build_medical_checklist,
    create_field_trip_consent,
)
from apps.schoolops.models import HealthRecord
from apps.schools.models import School


class FieldTripTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"FT {uid}", slug=f"ft-{uid}", subdomain=f"ft{uid}", is_active=True
        )
        year = AcademicYear.objects.create(
            name="Y1", start_date="2025-01-01", end_date="2025-12-31", school=self.school
        )
        dept = Department.objects.create(name="D", code=f"D{uid}", school=self.school)
        classroom = Classroom.objects.create(
            academic_year=year, department=dept, name="Grade 6", code=f"C{uid}", school=self.school
        )
        self.student = StudentProfile.objects.create(
            first_name="Liam",
            last_name="Mensah",
            date_of_birth="2013-05-01",
            student_code=f"ST{uid}",
            parent_phone="+233200111222",
            school=self.school,
            classroom=classroom,
        )
        self.healthy = StudentProfile.objects.create(
            first_name="Zoe",
            last_name="Ade",
            date_of_birth="2013-07-07",
            student_code=f"SH{uid}",
            school=self.school,
            classroom=classroom,
        )
        HealthRecord.objects.create(
            school=self.school, student=self.student, record_type="allergy", notes="Bee stings"
        )
        HealthRecord.objects.create(
            school=self.school, student=self.student, record_type="medication", notes="Ventolin inhaler"
        )

    def test_create_consent_request(self):
        req = create_field_trip_consent(
            school_id=self.school.id, title="Museum Trip", description="Year 6 outing"
        )
        self.assertIsInstance(req, ConsentRequest)
        self.assertEqual(req.category, "field_trip")
        self.assertEqual(req.title, "Museum Trip")
        self.assertTrue(req.is_active)

    def test_medical_checklist_compiles_real_data(self):
        checklist = build_medical_checklist(
            self.school.id, [self.student.id, self.healthy.id]
        )
        self.assertEqual(len(checklist), 2)
        by_name = {c["name"]: c for c in checklist}
        liam = by_name["Liam Mensah"]
        self.assertIn("Bee stings", liam["allergies"])
        self.assertIn("Ventolin inhaler", liam["medications"])
        self.assertEqual(liam["emergency_contact"], "+233200111222")
        self.assertTrue(liam["has_medical_flag"])
        # the healthy student has no medical flags
        zoe = by_name["Zoe Ade"]
        self.assertFalse(zoe["has_medical_flag"])
        self.assertEqual(zoe["allergies"], [])

    def test_checklist_scoped_to_requested_students(self):
        checklist = build_medical_checklist(self.school.id, [self.student.id])
        self.assertEqual(len(checklist), 1)
        self.assertEqual(checklist[0]["name"], "Liam Mensah")
