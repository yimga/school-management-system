from datetime import date

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile, TeacherProfile
from apps.schools.models import School
from apps.siteconfig.models import ServiceIntegration


class OneRosterViewsTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="OneRoster School",
            slug="or-school",
            subdomain="or-school",
            is_active=True,
        )
        self.integration = ServiceIntegration.objects.create(
            school=self.school,
            service_name="OneRoster Sync",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            client_secret="or-token",
            config={"bearer_token": "or-token"},
            is_active=True,
        )
        self.other_school = School.objects.create(
            name="OneRoster Other School",
            slug="or-other-school",
            subdomain="or-other-school",
            is_active=True,
        )
        self.other_integration = ServiceIntegration.objects.create(
            school=self.other_school,
            service_name="OneRoster Sync Other",
            service_type=ServiceIntegration.ServiceType.OAUTH,
            client_secret="or-other-token",
            config={"bearer_token": "or-other-token"},
            is_active=True,
        )
        self.year = AcademicYear.objects.create(
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 7, 31),
            is_active=True,
            school=self.school,
        )
        self.department = Department.objects.create(name="General", code="GEN-OR", school=self.school)
        self.classroom = Classroom.objects.create(
            name="Form 1",
            code="F1-OR",
            academic_year=self.year,
            department=self.department,
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            first_name="Nina",
            last_name="Roster",
            student_code="OR-STD-1",
            classroom=self.classroom,
            academic_year=self.year,
            is_active=True,
        )
        self.teacher_user = User.objects.create_user(
            username="teacher.or",
            email="teacher.or@example.com",
            password="x",
            role=User.Role.TEACHER,
        )
        self.teacher = TeacherProfile.objects.create(
            school=self.school,
            user=self.teacher_user,
            staff_id="T-OR-1",
            is_active=True,
        )

    def _headers(self, token="or-token"):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _url(self, name: str):
        return reverse(name) + f"?school_slug={self.school.slug}"

    def test_manifest_requires_token(self):
        response = self.client.get(self._url("api:oneroster-manifest"))
        self.assertEqual(response.status_code, 403)

    def test_manifest_returns_resource_links(self):
        response = self.client.get(self._url("api:oneroster-manifest"), **self._headers())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["oneroster_version"], "1.1")
        self.assertIn("classes", payload["resources"])

    def test_students_and_enrollments_return_rows(self):
        students = self.client.get(self._url("api:oneroster-students"), **self._headers())
        enrollments = self.client.get(self._url("api:oneroster-enrollments"), **self._headers())
        self.assertEqual(students.status_code, 200)
        self.assertEqual(enrollments.status_code, 200)
        self.assertEqual(students.json()["pagination"]["count"], 1)
        self.assertEqual(enrollments.json()["pagination"]["count"], 1)

    def test_teachers_returns_rows(self):
        response = self.client.get(self._url("api:oneroster-teachers"), **self._headers())
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["pagination"]["count"], 1)
        self.assertEqual(payload["users"][0]["username"], "teacher.or")

    def test_rejects_cross_tenant_token(self):
        response = self.client.get(
            reverse("api:oneroster-students") + f"?school_slug={self.other_school.slug}",
            **self._headers(token="or-token"),
        )
        self.assertEqual(response.status_code, 403)

    def test_oneroster_endpoints_rate_limit_429_when_exceeded(self):
        from unittest.mock import patch

        urls = [
            self._url("api:oneroster-manifest"),
            self._url("api:oneroster-classes"),
            self._url("api:oneroster-students"),
            self._url("api:oneroster-teachers"),
            self._url("api:oneroster-enrollments"),
        ]
        with patch("apps.api.oneroster_views.throttle_ip_request", return_value=(False, 30)):
            for url in urls:
                response = self.client.get(url, **self._headers())
                self.assertEqual(response.status_code, 429, msg=url)
                self.assertEqual(response["Retry-After"], "30", msg=url)
