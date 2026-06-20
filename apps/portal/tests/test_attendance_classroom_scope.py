"""Attendance classroom scoping: a regular teacher may only take attendance for
the classrooms they actually teach; oversight roles see every classroom.

Closes the gap where any attendance.manage holder could mark roll call for ANY
classroom (apps/portal/views_teacher.py::_attendance_visible_classrooms). Because
the POST handlers resolve the target classroom from this same list, the scoping
guards the write path as well as the display.
"""

from __future__ import annotations

from django.test import RequestFactory, TestCase

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
from apps.evals.models import TeacherAssignment
from apps.people.models import TeacherProfile
from apps.portal.views_teacher import _attendance_visible_classrooms


class AttendanceClassroomScopeTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-08-31",
            is_active=True,
        )
        self.term = Term.objects.create(
            academic_year=self.year,
            name="FIRST",
            position=1,
            start_date="2025-09-01",
            end_date="2025-11-30",
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="SCI")
        self.specialty = Specialty.objects.create(
            department=dept, name="Physics", code="PHY"
        )
        self.room_a = Classroom.objects.create(
            academic_year=self.year, department=dept, name="SS3A", code="SS3A"
        )
        self.room_b = Classroom.objects.create(
            academic_year=self.year, department=dept, name="SS3B", code="SS3B"
        )
        subject = Subject.objects.create(name="Physics")
        sa_a = SubjectAssignment.objects.create(
            academic_year=self.year,
            term=self.term,
            classroom=self.room_a,
            specialty=self.specialty,
            subject=subject,
            coefficient=1.0,
        )
        # Teacher assigned ONLY to room A.
        self.teacher_user = User.objects.create_user(
            "scope_teacher", "scope_teacher@example.com", "pass", role=User.Role.TEACHER
        )
        teacher_profile = TeacherProfile.objects.create(user=self.teacher_user)
        TeacherAssignment.objects.create(
            teacher=teacher_profile,
            academic_year=self.year,
            subject_assignment=sa_a,
            is_active=True,
        )
        # Teacher with NO assignments (e.g. an attendance officer modeled as a teacher).
        self.unassigned_teacher = User.objects.create_user(
            "no_assign_teacher", "noassign@example.com", "pass", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(user=self.unassigned_teacher)
        # Oversight role.
        self.admin_user = User.objects.create_user(
            "scope_admin", "scope_admin@example.com", "pass", role=User.Role.ADMIN
        )

    def _visible(self, user):
        request = self.factory.get("/portal/attendance/student/")
        request.user = user
        return {c.id for c in _attendance_visible_classrooms(request, self.year)}

    def test_assigned_teacher_sees_only_their_classroom(self):
        visible = self._visible(self.teacher_user)
        self.assertEqual(visible, {self.room_a.id})
        self.assertNotIn(self.room_b.id, visible)

    def test_admin_sees_all_classrooms(self):
        self.assertEqual(
            self._visible(self.admin_user), {self.room_a.id, self.room_b.id}
        )

    def test_unassigned_teacher_locked_down_by_default(self):
        # Locked down: a teacher with no active assignments sees NO classrooms,
        # not every classroom. Guards the attendance write path for stray teacher
        # accounts that were never assigned a class.
        self.assertEqual(self._visible(self.unassigned_teacher), set())

    def test_unassigned_teacher_sees_all_when_school_opts_in(self):
        # Opt-in escape hatch: a non-teaching attendance officer modeled as a
        # teacher can be restored to the legacy see-all behaviour per school.
        from apps.schools.models import School

        school = School.objects.create(
            name="Opt In Attendance School",
            slug="opt-in-attendance",
            subdomain="opt-in-attendance",
            is_active=True,
            settings={"attendance": {"unassigned_teacher_sees_all": True}},
        )
        request = self.factory.get("/portal/attendance/student/")
        request.user = self.unassigned_teacher
        request.school = school
        visible = {
            c.id for c in _attendance_visible_classrooms(request, self.year)
        }
        self.assertEqual(visible, {self.room_a.id, self.room_b.id})

    def test_no_active_year_returns_empty(self):
        request = self.factory.get("/portal/attendance/student/")
        request.user = self.teacher_user
        self.assertEqual(_attendance_visible_classrooms(request, None), [])
