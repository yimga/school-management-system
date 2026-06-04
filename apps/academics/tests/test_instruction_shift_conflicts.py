"""Shift-scoped scheduling conflicts (global kernel Phase 4)."""

from datetime import time

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from apps.academics.models import AcademicYear, Classroom, Subject, Term
from apps.academics.scheduling import (
    InstructionShift,
    Room,
    Schedule,
    ScheduleEntry,
    TimeSlot,
)

User = get_user_model()


class InstructionShiftConflictTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(
            username="shift_conflict_admin",
            password="unused",
            role="ADMIN",
        )
        self.teacher = User.objects.create_user(
            username="shift_conflict_teacher",
            password="unused",
            role="TEACHER",
        )
        self.room = Room.objects.create(
            name="Shift Room A",
            room_type="CLASSROOM",
            capacity=30,
        )
        self.slot = TimeSlot.objects.create(
            day_of_week=0,
            start_time=time(8, 0),
            end_time=time(9, 0),
            slot_name="Period 1",
        )
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Shift School",
            slug="shift-school",
            subdomain="shift-school",
            is_active=True,
        )
        self.shift_morning = InstructionShift.objects.create(
            school=self.school,
            code="morning",
            label="Morning",
        )
        self.shift_afternoon = InstructionShift.objects.create(
            school=self.school,
            code="afternoon",
            label="Afternoon",
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
        dept = None
        from apps.academics.models import Department

        dept = Department.objects.create(
            school=self.school,
            code=f"GEN-{str(self.school.id)[:8]}",
            name="General",
        )
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=year,
            department=dept,
            name="Form 1",
            code="form-1",
        )
        self.subject = Subject.objects.create(
            school=self.school,
            name="Math",
            category="GENERAL",
        )

    def _schedule(self, shift):
        return Schedule.objects.create(
            name=f"Sched {shift.code}",
            academic_year=self.term.academic_year,
            term=self.term,
            shift=shift,
            created_by=self.admin,
        )

    def test_same_room_different_shifts_allowed(self):
        sched_a = self._schedule(self.shift_morning)
        sched_b = self._schedule(self.shift_afternoon)
        ScheduleEntry.objects.create(
            schedule=sched_a,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        entry_b = ScheduleEntry(
            schedule=sched_b,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        entry_b.full_clean()

    def test_same_room_same_shift_blocks(self):
        sched = self._schedule(self.shift_morning)
        ScheduleEntry.objects.create(
            schedule=sched,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        duplicate = ScheduleEntry(
            schedule=sched,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher,
            room=self.room,
            time_slot=self.slot,
        )
        with self.assertRaises(ValidationError):
            duplicate.full_clean()
