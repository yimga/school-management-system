"""Absence → substitute market auto-open (metric 12 residual)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase

from apps.academics.models import Department
from apps.people.models import TeacherAttendance, TeacherProfile
from apps.schoolops.absence_auto_open import maybe_open_market_for_teacher_absence
from apps.schoolops.substitute_market import list_open_shifts
from apps.schools.models import School

User = get_user_model()


class AbsenceAutoOpenTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Auto Open School",
            slug="auto-open-school",
            subdomain="auto-open-school",
            is_active=True,
        )
        self.teacher_user = User.objects.create_user(
            username="absent_auto",
            password="testpass123",
            role=User.Role.TEACHER,
        )
        dept = Department.objects.create(school=self.school, name="STEM", code="AO")
        self.profile = TeacherProfile.objects.create(
            school=self.school,
            user=self.teacher_user,
            department=dept,
            is_active=True,
            phone="+237600000200",
        )
        self.work_date = date(2026, 7, 18)

    def test_maybe_open_opens_shift_for_absent(self):
        att = TeacherAttendance(
            teacher=self.profile,
            date=self.work_date,
            status=TeacherAttendance.Status.ABSENT,
        )
        with patch(
            "apps.schoolops.substitute_handover.broadcast_substitute_request",
            return_value=[],
        ):
            shift = maybe_open_market_for_teacher_absence(
                att, notify=True, publish_fn=lambda _p: None
            )
        self.assertIsNotNone(shift)
        open_rows = list_open_shifts(school_id=int(self.school.pk))
        self.assertEqual(len(open_rows), 1)
        self.assertEqual(open_rows[0]["absent_teacher_id"], self.teacher_user.pk)

    def test_present_does_not_open(self):
        att = TeacherAttendance(
            teacher=self.profile,
            date=self.work_date,
            status=TeacherAttendance.Status.PRESENT,
        )
        shift = maybe_open_market_for_teacher_absence(att, publish_fn=lambda _p: None)
        self.assertIsNone(shift)
        self.assertEqual(list_open_shifts(school_id=int(self.school.pk)), [])

    def test_signal_opens_on_absent_create(self):
        with patch(
            "apps.schoolops.substitute_handover.broadcast_substitute_request",
            return_value=[],
        ):
            TeacherAttendance.objects.create(
                teacher=self.profile,
                date=self.work_date,
                status=TeacherAttendance.Status.ABSENT,
            )
        open_rows = list_open_shifts(school_id=int(self.school.pk))
        self.assertEqual(len(open_rows), 1)
