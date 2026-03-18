"""
Tests for teacher timetable view (portal:teacher_timetable).
"""

from datetime import date, time

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Term,
    Classroom,
    Subject,
    Department,
    Specialty,
)
from apps.people.models import TeacherProfile

from apps.academics.scheduling import Schedule, ScheduleEntry, Room, TimeSlot


class TeacherTimetableViewTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name=Term.Name.FIRST,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="SCI")
        Specialty.objects.create(name="General", code="GEN", department=dept)
        self.classroom = Classroom.objects.create(
            name="Form 1A",
            code="F1A",
            academic_year=self.year,
            department=dept,
        )
        self.subject = Subject.objects.create(name="Mathematics")
        self.room = Room.objects.create(
            name="Room 101",
            room_type="CLASSROOM",
            capacity=30,
        )
        self.slot = TimeSlot.objects.create(
            day_of_week=0,  # Monday
            start_time=time(8, 0),
            end_time=time(9, 0),
            slot_name="Period 1",
        )
        self.teacher_user = User.objects.create_user(
            username="teacher_tt", password="test"
        )
        self.teacher_user.role = User.Role.TEACHER
        self.teacher_user.save(update_fields=["role"])
        TeacherProfile.objects.create(user=self.teacher_user)
        self.other_teacher = User.objects.create_user(
            username="teacher_other", password="test"
        )
        self.other_teacher.role = User.Role.TEACHER
        self.other_teacher.save(update_fields=["role"])
        TeacherProfile.objects.create(user=self.other_teacher)

    def test_timetable_requires_teacher_login(self):
        url = reverse("portal:teacher_timetable")
        resp = self.client.get(url)
        self.assertIn(resp.status_code, (302, 403))

    def test_timetable_200_when_no_schedule(self):
        self.client.force_login(self.teacher_user)
        resp = self.client.get(reverse("portal:teacher_timetable"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "My Timetable")

    def test_timetable_shows_entry_for_logged_in_teacher(self):
        schedule = Schedule.objects.create(
            name="Term 1 Schedule",
            academic_year=self.year,
            term=self.term,
            status="PUBLISHED",
            created_by=self.teacher_user,
        )
        ScheduleEntry.objects.create(
            schedule=schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.teacher_user,
            room=self.room,
            time_slot=self.slot,
        )
        self.client.force_login(self.teacher_user)
        resp = self.client.get(reverse("portal:teacher_timetable"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Mathematics")
        self.assertContains(resp, "Form 1A")
        self.assertContains(resp, "Room 101")

    def test_timetable_does_not_show_other_teacher_entry(self):
        schedule = Schedule.objects.create(
            name="Term 1 Schedule",
            academic_year=self.year,
            term=self.term,
            status="PUBLISHED",
            created_by=self.teacher_user,
        )
        ScheduleEntry.objects.create(
            schedule=schedule,
            classroom=self.classroom,
            subject=self.subject,
            teacher=self.other_teacher,
            room=self.room,
            time_slot=self.slot,
        )
        self.client.force_login(self.teacher_user)
        resp = self.client.get(reverse("portal:teacher_timetable"))
        self.assertEqual(resp.status_code, 200)
        self.assertNotContains(resp, "Mathematics")
