from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Term, Department, Specialty, Classroom
from apps.people.models import StudentProfile, StudentGuardian


class UrlAliasTests(TestCase):
    def test_student_portal_grades_alias_redirects(self):
        resp = self.client.get("/portal/student-portal/grades/", follow=True)
        # Expect redirect to login since dashboard requires auth
        self.assertEqual(resp.redirect_chain[0][0], reverse("accounts:login") + "?next=/portal/student-portal/grades/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "name=\"username\"")

    def test_admissions_application_status_alias_redirects(self):
        resp = self.client.get("/portal/admissions/application-status/", follow=True)
        self.assertEqual(resp.redirect_chain[0][0], reverse("accounts:login") + "?next=/portal/admissions/application-status/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "name=\"username\"")

    def test_alias_renders_parent_dashboard_when_authenticated(self):
        year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        Term.objects.create(
            academic_year=year,
            name=Term.Name.FIRST,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="SCI")
        spec = Specialty.objects.create(name="General", code="GEN", department=dept)
        classroom = Classroom.objects.create(
            name="Form 1",
            code="F1",
            academic_year=year,
            department=dept,
        )
        parent_user = User.objects.create_user(username="parent", password="pass")
        parent_user.role = User.Role.PARENT
        parent_user.save(update_fields=["role"])
        student = StudentProfile.objects.create(
            first_name="Kid",
            last_name="One",
            student_code="STD100",
            academic_year=year,
            classroom=classroom,
            specialty=spec,
        )
        StudentGuardian.objects.create(
            guardian_user=parent_user,
            student=student,
            can_view_results=True,
        )

        self.client.force_login(parent_user)
        resp = self.client.get("/portal/student-portal/grades/", follow=True)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Parent Dashboard")
