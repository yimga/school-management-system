from datetime import date

from django.test import TestCase

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Term, Department, Specialty, Classroom
from apps.people.models import TeacherProfile, StudentProfile, StudentGuardian


class AccessSmokeTests(TestCase):
    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        self.term = Term.objects.create(
            name=Term.Name.FIRST,
            academic_year=self.year,
            start_date=date(2025, 9, 1),
            end_date=date(2025, 12, 1),
            is_active=True,
        )
        dept = Department.objects.create(name="Science", code="SCI")
        spec = Specialty.objects.create(name="General", code="GEN", department=dept)
        self.classroom = Classroom.objects.create(
            name="Form 1",
            code="F1",
            academic_year=self.year,
            department=dept,
        )

    def test_admin_requires_login(self):
        resp = self.client.get("/admin/")
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/admin/login/", resp.url)
        login = self.client.get("/admin/login/?next=/admin/")
        self.assertEqual(login.status_code, 200)

    def test_teacher_dashboard_access(self):
        teacher_user = User.objects.create_user(username="teach", password="pass")
        teacher_user.role = User.Role.TEACHER
        teacher_user.save(update_fields=["role"])
        TeacherProfile.objects.create(user=teacher_user)

        self.client.force_login(teacher_user)
        resp = self.client.get("/portal/teacher/")
        self.assertNotEqual(resp.status_code, 403)

        # Parent cannot access teacher dashboard
        parent_user = User.objects.create_user(username="parent", password="pass2")
        parent_user.role = User.Role.PARENT
        parent_user.save(update_fields=["role"])
        self.client.force_login(parent_user)
        resp_forbidden = self.client.get("/portal/teacher/")
        self.assertIn(resp_forbidden.status_code, [302, 403])

    def test_parent_dashboard_access(self):
        parent_user = User.objects.create_user(username="parent2", password="pass3")
        parent_user.role = User.Role.PARENT
        parent_user.save(update_fields=["role"])
        student = StudentProfile.objects.create(
            first_name="Kid",
            last_name="One",
            student_code="STD200",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=Specialty.objects.get(code="GEN"),
        )
        StudentGuardian.objects.create(
            guardian_user=parent_user,
            student=student,
            can_view_results=True,
        )

        self.client.force_login(parent_user)
        resp = self.client.get("/portal/parent/")
        self.assertEqual(resp.status_code, 200)

        # Teacher should not see parent dashboard content
        teacher_user = User.objects.create_user(username="teach2", password="pass4")
        teacher_user.role = User.Role.TEACHER
        teacher_user.save(update_fields=["role"])
        TeacherProfile.objects.create(user=teacher_user)
        self.client.force_login(teacher_user)
        forbidden = self.client.get("/portal/parent/")
        self.assertIn(forbidden.status_code, [302, 403])
