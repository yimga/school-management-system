"""DB-level schedule conflict constraints (partial unique / EXCLUDE-adjacent)."""

from datetime import time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Department, Subject, Term
from apps.academics.scheduling import (
    InstructionShift,
    Room,
    Schedule,
    ScheduleEntry,
    TimeSlot,
)
from apps.schools.models import School

User = get_user_model()


class SchedulingDbConstraintTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="sched_db_admin",
            password="unused",
            role="ADMIN",
        )
        self.teacher = User.objects.create_user(
            username="sched_db_teacher",
            password="unused",
            role="TEACHER",
        )
        self.room = Room.objects.create(
            name="DB Constraint Room",
            room_type="CLASSROOM",
            capacity=30,
        )
        self.slot = TimeSlot.objects.create(
            day_of_week=1,
            start_time=time(10, 0),
            end_time=time(11, 0),
            slot_name="Period 2",
        )
        self.school = School.objects.create(
            name="DB Constraint School",
            slug="db-constraint-school",
            subdomain="db-constraint-school",
            is_active=True,
        )
        self.shift = InstructionShift.objects.create(
            school=self.school,
            code="morning",
            label="Morning",
        )
        year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-06-30",
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=year,
            name="Term 1",
            position=1,
            start_date="2025-09-01",
            end_date="2025-12-15",
            is_active=True,
        )
        dept = Department.objects.create(
            school=self.school,
            code="GEN-DB",
            name="General",
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=year,
            department=dept,
            name="Form 2",
            code="form-2",
        )
        self.subject = Subject.objects.create(
            school=self.school,
            name="Science",
            category="GENERAL",
        )
        self.schedule = Schedule.objects.create(
            name="Shift schedule",
            academic_year=year,
            term=self.term,
            shift=self.shift,
            created_by=self.admin,
        )

    def test_duplicate_room_same_shift_raises_integrity_error(self):
        ScheduleEntry.objects.create(
            schedule=self.schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        duplicate = ScheduleEntry(
            schedule=self.schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                duplicate.save()

    def test_duplicate_room_same_shift_full_clean_still_raises(self):
        ScheduleEntry.objects.create(
            schedule=self.schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        duplicate = ScheduleEntry(
            schedule=self.schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()

    def test_denormalized_term_and_shift_populated_on_save(self):
        entry = ScheduleEntry.objects.create(
            schedule=self.schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.term_id, self.term.pk)
        self.assertEqual(entry.instruction_shift_id, self.shift.pk)
