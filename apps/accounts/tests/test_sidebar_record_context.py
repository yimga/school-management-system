"""Context rail: sidebar quick links when path matches Student 360."""

from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory, TestCase

from apps.accounts.context_processors import sidebar_record_context
from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department, Specialty, Term
from apps.people.models import StudentProfile
from apps.schools.models import School

from datetime import date


class SidebarRecordContextTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Ctx School",
            slug="ctx-school",
            subdomain="ctx-school",
            is_active=True,
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
        dept = Department.objects.create(name="Science", code="SCI")
        spec = Specialty.objects.create(name="General", code="GEN", department=dept)
        classroom = Classroom.objects.create(
            name="F1", code="F1", academic_year=year, department=dept
        )
        self.student = StudentProfile.objects.create(
            first_name="Alex",
            last_name="River",
            student_code="CTX001",
            school=self.school,
            academic_year=year,
            classroom=classroom,
            specialty=spec,
        )
        self.user = User.objects.create_user(username="staffctx", password="x")
        self.user.is_authenticated = True  # type: ignore[attr-defined]

    def test_anonymous_returns_none(self):
        req = self.factory.get(f"/authentication/backend/students/{self.student.pk}/")
        req.user = AnonymousUser()
        req.school = self.school
        self.assertIsNone(sidebar_record_context(req)["sidebar_record_context"])

    def test_matching_student_includes_transcript_and_discipline_links(self):
        req = self.factory.get(f"/authentication/backend/students/{self.student.pk}/")
        req.user = self.user
        req.school = self.school
        ctx = sidebar_record_context(req)["sidebar_record_context"]
        self.assertIsNotNone(ctx)
        labels = {l["label"] for l in ctx["links"]}
        self.assertIn("Transcript archive", labels)
        self.assertIn("Discipline incidents", labels)
        self.assertIn("Student 360", labels)

    def test_wrong_school_student_returns_none(self):
        other = School.objects.create(
            name="Other",
            slug="other-sch",
            subdomain="other-sch",
            is_active=True,
        )
        req = self.factory.get(f"/authentication/backend/students/{self.student.pk}/")
        req.user = self.user
        req.school = other
        self.assertIsNone(sidebar_record_context(req)["sidebar_record_context"])
