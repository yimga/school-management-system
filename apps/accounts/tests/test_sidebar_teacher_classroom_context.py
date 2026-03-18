"""Sidebar context rail for teacher and classroom backend URLs."""

import uuid
from datetime import date

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.accounts.context_processors import sidebar_record_context
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Term
from apps.people.models import TeacherProfile
from apps.schools.models import School


class SidebarTeacherClassroomContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Rail School",
            slug="rail-school",
            subdomain="rail-school",
            is_active=True,
        )
        self.viewer = User.objects.create_user(username="rail_viewer", password="x")
        self.teacher_user = User.objects.create_user(
            username="rail_teacher", password="x"
        )
        year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=year,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        dept = Department.objects.create(
            name="Science",
            code=f"R{uuid.uuid4().hex[:8]}",
            school=self.school,
        )
        self.teacher = TeacherProfile.objects.create(
            user=self.teacher_user,
            school=self.school,
            staff_id="T1RAIL",
            department=dept,
        )
        self.classroom = Classroom.objects.create(
            name="Form 1A",
            code=f"F1{uuid.uuid4().hex[:6]}",
            school=self.school,
            academic_year=year,
            department=dept,
        )

    def test_teacher_path_sets_context(self):
        req = self.factory.get(f"/authentication/backend/teachers/{self.teacher.pk}/")
        req.user = self.viewer
        req.school = self.school
        ctx = sidebar_record_context(req)["sidebar_record_context"]
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["title"], "This teacher")
        labels = {x["label"] for x in ctx["links"]}
        self.assertIn("Teacher overview", labels)

    def test_classroom_path_sets_context(self):
        req = self.factory.get(
            f"/authentication/backend/classrooms/{self.classroom.pk}/"
        )
        req.user = self.viewer
        req.school = self.school
        ctx = sidebar_record_context(req)["sidebar_record_context"]
        self.assertIsNotNone(ctx)
        self.assertEqual(ctx["title"], "This class")
        labels = {x["label"] for x in ctx["links"]}
        self.assertIn("Students in this class", labels)

    def test_anonymous_empty(self):
        req = self.factory.get(f"/authentication/backend/teachers/{self.teacher.pk}/")
        req.user = AnonymousUser()
        req.school = self.school
        self.assertIsNone(sidebar_record_context(req)["sidebar_record_context"])
