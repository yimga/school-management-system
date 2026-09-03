"""Schedule DFV → ScheduleEntry materialization — 2026-09-03."""

from __future__ import annotations

import uuid
from datetime import date

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.academics.models import (
    Classroom,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
)
from apps.academics.scheduling import ScheduleEntry
from apps.evals.models import TeacherAssignment
from apps.metadata.models import DynamicFieldDefinition, DynamicFieldValue
from apps.migration_cloud.schedule_materializer import materialize_schedule_from_import_dfv
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School


def _school(tag: str) -> School:
    slug = f"{tag}-{uuid.uuid4().hex[:8]}"
    return School.objects.create(
        name=f"School {slug}",
        slug=slug,
        subdomain=slug,
        country_code="CM",
    )


class ScheduleMaterializerTests(TestCase):
    def test_materializes_when_refs_resolve(self):
        school = _school("sched-mat")
        from apps.academics.models import AcademicYear, Term

        year = AcademicYear.objects.create(
            school=school,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        term = Term.objects.create(
            school=school,
            academic_year=year,
            name="T1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        dept = Department.objects.create(school=school, name="GEN", code="GEN")
        classroom = Classroom.objects.create(
            school=school,
            name="Form 2A",
            code="F2A",
            academic_year=year,
            department=dept,
        )
        specialty = Specialty.objects.create(
            school=school, name="PLUMBING", code="PL", department=dept
        )
        subject = Subject.objects.create(school=school, name="Mathematics", code="MATH")
        student = StudentProfile.objects.create(
            school=school,
            first_name="Stu",
            last_name="One",
            student_code="S-1",
            academic_year=year,
            classroom=classroom,
            specialty=specialty,
            is_active=True,
        )
        self.assertIsNotNone(student.pk)

        teacher_user = get_user_model().objects.create_user(
            username=f"t-{uuid.uuid4().hex[:8]}",
            password="test-pass",
        )
        teacher = TeacherProfile.objects.create(
            school=school, staff_id="T-1", user=teacher_user
        )
        assignment = SubjectAssignment.objects.create(
            school=school,
            academic_year=year,
            term=term,
            classroom=classroom,
            specialty=specialty,
            subject=subject,
            coefficient=1,
        )
        TeacherAssignment.objects.create(
            school=school,
            teacher=teacher,
            academic_year=year,
            subject_assignment=assignment,
            is_active=True,
        )

        DynamicFieldDefinition.objects.create(
            school=school,
            entity_type="schedule",
            field_key="record",
            label="Record",
            data_type="json",
        )
        DynamicFieldValue.objects.create(
            school=school,
            entity_type="schedule",
            entity_id="F2A:Monday:08:30",
            field_key="record",
            value_json={
                "v": {
                    "section_external_id": "Form 2A",
                    "day_of_week": "Monday",
                    "start_time": "08:30",
                    "end_time": "09:30",
                    "room": "Lab-2",
                    "subject": "Mathematics",
                }
            },
        )

        outcome = materialize_schedule_from_import_dfv(school)
        self.assertGreaterEqual(outcome.get("schedule_entries_created", 0), 1)
        self.assertTrue(
            ScheduleEntry.objects.filter(
                classroom=classroom, subject=subject, teacher=teacher_user
            ).exists()
        )
