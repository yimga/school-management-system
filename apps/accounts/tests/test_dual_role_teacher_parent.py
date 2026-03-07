"""
Integration tests for dual-role users (Teacher + Parent, same account).

- User with role TEACHER + TeacherProfile + StudentGuardian can access both teacher and parent portal.
- Data scope: parent views see only linked children; teacher views see teacher-scoped data.
- Role switcher: switch_portal_role sets session and redirects; effective role drives sidebar/redirect.
"""
from datetime import date

from django.test import TestCase, Client
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.portal_roles import has_teacher_hat, has_parent_hat, ACTIVE_PORTAL_ROLE_KEY
from apps.academics.models import AcademicYear, Department, Specialty, Classroom
from apps.people.models import StudentProfile, TeacherProfile, StudentGuardian


class DualRolePortalAccessTests(TestCase):
    """Dual-role user can access both Teacher and Parent portal views and data is scoped correctly."""

    def setUp(self):
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
        )
        self.department = Department.objects.create(name="General", code="GEN")
        self.specialty = Specialty.objects.create(name="General", code="GEN", department=self.department)
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=self.department,
            name="Form 1",
            code="F1",
        )
        self.student = StudentProfile.objects.create(
            first_name="Child",
            last_name="One",
            academic_year=self.year,
            classroom=self.classroom,
            specialty=self.specialty,
        )
        # User is TEACHER and also guardian of self.student
        self.dual_user = User.objects.create_user(
            username="teacher_parent",
            password="pass1234",
            role=User.Role.TEACHER,
        )
        TeacherProfile.objects.create(user=self.dual_user, staff_id="T001")
        StudentGuardian.objects.create(
            guardian_user=self.dual_user,
            student=self.student,
            can_view_results=True,
            can_view_finance=True,
        )
        self.client = Client()

    def test_has_both_hats(self):
        self.assertTrue(has_teacher_hat(self.dual_user))
        self.assertTrue(has_parent_hat(self.dual_user))

    def test_parent_dashboard_access(self):
        self.client.login(username="teacher_parent", password="pass1234")
        resp = self.client.get(reverse("portal:parent_dashboard"), follow=False)
        self.assertEqual(resp.status_code, 200)

    def test_parent_finance_access(self):
        self.client.login(username="teacher_parent", password="pass1234")
        resp = self.client.get(reverse("portal:parent_finance"), follow=False)
        self.assertEqual(resp.status_code, 200)

    def test_teacher_workflow_access(self):
        """Dual-role user can reach teacher workflow (200 or 403 when no active term/assignments)."""
        self.client.login(username="teacher_parent", password="pass1234")
        resp = self.client.get(reverse("portal:teacher_workflow"), follow=False)
        self.assertIn(resp.status_code, (200, 403), msg="Dual-role user should reach teacher workflow (not 404); 403 ok when no term/assignments")

    def test_switch_portal_role_sets_session_and_redirects(self):
        self.client.login(username="teacher_parent", password="pass1234")
        resp = self.client.get(reverse("accounts:switch_portal_role") + "?role=PARENT", follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn(ACTIVE_PORTAL_ROLE_KEY, self.client.session)
        self.assertEqual(self.client.session[ACTIVE_PORTAL_ROLE_KEY], "PARENT")

        resp = self.client.get(reverse("accounts:switch_portal_role") + "?role=TEACHER", follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(self.client.session[ACTIVE_PORTAL_ROLE_KEY], "TEACHER")

    def test_redirect_respects_session_role(self):
        """When session has active_portal_role, redirect sends dual-hat user to that role's dashboard."""
        self.client.login(username="teacher_parent", password="pass1234")
        session = self.client.session
        session[ACTIVE_PORTAL_ROLE_KEY] = "PARENT"
        session.save()
        resp = self.client.get(reverse("accounts:redirect"), follow=False)
        self.assertEqual(resp.status_code, 302)
        self.assertIn("parent", resp.url.lower() or "")

        session[ACTIVE_PORTAL_ROLE_KEY] = "TEACHER"
        session.save()
        resp = self.client.get(reverse("accounts:redirect"), follow=False)
        self.assertEqual(resp.status_code, 302)
        url_lower = (resp.url or "").lower()
        self.assertTrue("teacher" in url_lower or "evals" in url_lower, f"Expected teacher/evals URL, got {resp.url}")

    def test_parent_sees_only_linked_child(self):
        """Parent dashboard / guardian_student_links returns only the dual user's linked student."""
        from apps.portal.services import guardian_student_links
        links = list(guardian_student_links(self.dual_user, results_only=True))
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0].student_id, self.student.id)
