"""Critical-path tests for academics (syllabus, grading, get_active_year_and_term).

Covers III.39: Deepen tests for academics critical paths.
"""

import uuid
from datetime import date

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.academics.models import (
    AcademicYear,
    Classroom,
    CourseSyllabus,
    Department,
    Specialty,
    Subject,
    SubjectAssignment,
    Term,
)
from apps.academics.services import get_active_year_and_term
from apps.accounts.models import User
from apps.evals.models import TeacherAssignment
from apps.people.models import TeacherProfile
from apps.schools.models import School


class GetActiveYearAndTermTests(TestCase):
    """get_active_year_and_term is used by syllabus hub, reports, and evals."""

    def test_returns_none_when_no_data(self):
        """Scoped to a school with no academic years (DB may have other schools' data from migrations)."""
        school = School.objects.create(
            name="No Academic Data School",
            slug="no-academic-data",
            subdomain="no-academic-data",
            is_active=True,
        )
        year, term = get_active_year_and_term(school=school)
        self.assertIsNone(year)
        self.assertIsNone(term)

    def test_returns_year_and_term_when_configured(self):
        school = School.objects.create(
            name="Test School",
            slug="test-school",
            subdomain="test-school",
            is_active=True,
        )
        yr = AcademicYear.objects.create(
            school=school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        tr = Term.objects.create(
            school=school,
            academic_year=yr,
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        year, term = get_active_year_and_term(school=school)
        self.assertIsNotNone(year)
        self.assertEqual(year.id, yr.id)
        self.assertIsNotNone(term)
        self.assertEqual(term.id, tr.id)


class SyllabusHubCriticalPathTests(TestCase):
    """Teacher syllabus hub and workflow (III.39 critical path)."""

    def setUp(self):
        self.school = School.objects.create(
            name="Syllabus Test School",
            slug="syllabus-test",
            subdomain="syllabus-test",
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
        )
        self.term = Term.objects.create(
            school=self.school,
            academic_year=self.year,
            name="Term 1",
            position=1,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 15),
            is_active=True,
        )
        self.dept = Department.objects.create(school=self.school, name="Math", code="M")
        self.classroom = Classroom.objects.create(
            school=self.school,
            academic_year=self.year,
            department=self.dept,
            name="Grade 10",
            code="G10",
        )
        self.specialty = Specialty.objects.create(
            school=self.school,
            department=self.dept,
            name="General",
            code=f"SYL-{uuid.uuid4().hex[:12]}",
        )
        self.subject = Subject.objects.create(school=self.school, name="Algebra")
        self.subject_assignment = SubjectAssignment.objects.create(
            school=self.school,
            classroom=self.classroom,
            subject=self.subject,
            term=self.term,
            academic_year=self.year,
            specialty=self.specialty,
        )
        self.teacher_user = User.objects.create_user(
            username="teacher_syllabus",
            email="teacher_syllabus@test.com",
            password="testpass123",
            is_staff=True,
            role=User.Role.TEACHER,
        )
        self.other_user = User.objects.create_user(
            username="other_user",
            email="other@test.com",
            password="testpass123",
            is_staff=True,
        )

    @override_settings(ROOT_URLCONF="config.urls")
    def test_teacher_syllabus_hub_forbidden_without_teacher_profile(self):
        """User without TeacherProfile gets 403."""
        self.client.login(username="other_user", password="testpass123")
        response = self.client.get(reverse("academics:teacher_syllabus_hub"))
        self.assertEqual(response.status_code, 403)

    @override_settings(ROOT_URLCONF="config.urls")
    def test_teacher_syllabus_hub_200_with_teacher_profile(self):
        """Teacher with profile (and optional assignments) gets 200 and hub page."""
        profile = TeacherProfile.objects.create(user=self.teacher_user, school=self.school)
        TeacherAssignment.objects.create(
            school=self.school,
            teacher=profile,
            academic_year=self.year,
            subject_assignment=self.subject_assignment,
            is_active=True,
        )
        self.client.login(username="teacher_syllabus", password="testpass123")
        response = self.client.get(reverse("academics:teacher_syllabus_hub"))
        self.assertEqual(response.status_code, 200)
        # render() returns HttpResponse; test client does not attach template context.
        self.assertContains(response, "Course syllabi")
        self.assertContains(response, "Algebra")

    @override_settings(ROOT_URLCONF="config.urls")
    def test_syllabus_builder_200_for_assigned_teacher(self):
        """Syllabus builder GET loads when teacher has an active assignment (III.39)."""
        profile = TeacherProfile.objects.create(user=self.teacher_user, school=self.school)
        TeacherAssignment.objects.create(
            school=self.school,
            teacher=profile,
            academic_year=self.year,
            subject_assignment=self.subject_assignment,
            is_active=True,
        )
        self.client.login(username="teacher_syllabus", password="testpass123")
        url = reverse(
            "academics:syllabus_builder",
            kwargs={"subject_assignment_id": self.subject_assignment.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        # Builder template should surface subject name from assignment (stable across locales).
        self.assertContains(response, "Algebra", html=False)

    @override_settings(ROOT_URLCONF="config.urls")
    def test_syllabus_builder_403_when_user_not_assigned(self):
        """Builder refuses users who are not assigned to the subject (III.39)."""
        self.client.login(username="other_user", password="testpass123")
        url = reverse(
            "academics:syllabus_builder",
            kwargs={"subject_assignment_id": self.subject_assignment.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)

    @override_settings(ROOT_URLCONF="config.urls")
    def test_syllabus_preview_200_for_assigned_teacher_with_syllabus(self):
        """Preview requires a CourseSyllabus row; owner teacher gets 200 (III.39)."""
        profile = TeacherProfile.objects.create(user=self.teacher_user, school=self.school)
        TeacherAssignment.objects.create(
            school=self.school,
            teacher=profile,
            academic_year=self.year,
            subject_assignment=self.subject_assignment,
            is_active=True,
        )
        CourseSyllabus.objects.create(
            subject_assignment=self.subject_assignment,
            status=CourseSyllabus.Status.DRAFT,
            created_by=self.teacher_user,
        )
        self.client.login(username="teacher_syllabus", password="testpass123")
        url = reverse(
            "academics:syllabus_preview",
            kwargs={"subject_assignment_id": self.subject_assignment.id},
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Algebra", html=False)
