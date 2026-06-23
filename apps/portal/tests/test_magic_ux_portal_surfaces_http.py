"""Magic UX: portal shells via HTTP (teacher, student, parent finance surfaces)."""

from __future__ import annotations

import uuid
from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership


class TeacherAttendanceMagicUxHttpTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.school = School.objects.create(
            name="MUX Teacher School",
            slug="mux-teacher",
            subdomain="mux-teacher",
            is_active=True,
        )
        self.teacher = User.objects.create_user(
            username="mux_teacher_att",
            password="testpass12",
        )
        self.teacher.role = User.Role.TEACHER
        self.teacher.save(update_fields=["role"])
        TeacherProfile.objects.create(
            user=self.teacher,
            school=self.school,
            staff_id="MUX-T1",
        )
        SchoolMembership.objects.get_or_create(
            user=self.teacher,
            school=self.school,
            defaults={"role": User.Role.TEACHER, "is_primary": True},
        )

    def test_attendance_page_has_task_marker_and_empty_state_without_logs(self):
        self.client.force_login(self.teacher)
        url = reverse("portal:teacher_attendance")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:800])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-task="teacher_attendance"', body)
        self.assertIn("rmc-empty", body)
        self.assertIn("No attendance history yet", body)


class StudentLearningHomeMagicUxHttpTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.student = User.objects.create_user(
            username="mux_student_lh",
            password="testpass12",
        )
        self.student.role = User.Role.STUDENT
        self.student.save(update_fields=["role"])

    def test_student_grades_route_renders_learning_home_markers(self):
        self.client.force_login(self.student)
        url = reverse("portal:student_portal_grades")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn('data-rmc-student-learning-home="1"', body)
        self.assertIn('data-page-archetype="student-dashboard"', body)
        self.assertIn('class="rmc-dh', body)


class ParentFinanceMagicUxHttpTests(TestCase):
    databases = {"default"}

    @classmethod
    def setUpTestData(cls):
        cls.school = School.objects.create(
            name="MUX Parent Finance School",
            slug="mux-pfin",
            subdomain="mux-pfin",
            is_active=True,
        )
        cls.year = AcademicYear.objects.create(
            school=cls.school,
            name="2025-2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        dept = Department.objects.create(
            school=cls.school,
            name="Core",
            code=f"MUXPF-{uuid.uuid4().hex[:8]}",
        )
        sp = Specialty.objects.create(department=dept, name="General", code="GN")
        cls.classroom = Classroom.objects.create(
            school=cls.school,
            academic_year=cls.year,
            department=dept,
            name="Form 1",
            code="F1",
        )
        cls.student = StudentProfile.objects.create(
            school=cls.school,
            first_name="Kid",
            last_name="Student",
            student_code=f"MUX-KID-{uuid.uuid4().hex[:8]}",
            academic_year=cls.year,
            classroom=cls.classroom,
            specialty=sp,
            date_of_birth=date(2012, 1, 15),
            is_active=True,
        )
        cls.parent = User.objects.create_user(
            username="mux_parent_fin",
            password="testpass12",
        )
        cls.parent.role = User.Role.PARENT
        cls.parent.save(update_fields=["role"])
        SchoolMembership.objects.get_or_create(
            user=cls.parent,
            school=cls.school,
            defaults={"role": User.Role.PARENT, "is_primary": True},
        )
        StudentGuardian.objects.create(
            guardian_user=cls.parent,
            student=cls.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
            can_view_finance=True,
        )

    @override_settings(CONVERSION_SINGLE_ACTION_ENFORCED=True)
    def test_strict_toolbar_jump_invoices_and_more_actions(self):
        self.client.force_login(self.parent)
        url = reverse("portal:parent_finance")
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200, msg=getattr(resp, "content", b"")[:800])
        body = resp.content.decode("utf-8", errors="replace")
        self.assertIn("rmc-conversion-more-actions", body)
        self.assertIn('data-action="jump-invoices"', body)
        self.assertIn('id="parent-finance-invoices"', body)
        self.assertIn('data-task="parent_payment"', body)
