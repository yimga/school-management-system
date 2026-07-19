"""#19 Privacy — HTTP soak for multi-subject erasure request UI."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.academics.models import AcademicYear
from apps.compliance.models import EraseRequest
from apps.people.models import StudentGuardian, StudentProfile, TeacherProfile
from apps.schools.models import School, SchoolMembership
from apps.schools.session_school_bind import sign_session_school_bind


User = get_user_model()


class ErasureRequestHttpSoakTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Erase Soak {uid}",
            slug=f"erase-soak-{uid}",
            subdomain=f"es{uid}",
            is_active=True,
        )
        self.admin = User.objects.create_user(
            username=f"erase_admin_{uid}",
            password="Test1234",
            role=User.Role.ADMIN,
            is_staff=True,
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role="ADMIN", is_primary=True
        )
        self.year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date="2025-09-01",
            end_date="2026-07-31",
            is_active=True,
        )
        self.student_user = User.objects.create_user(
            username=f"erase_stu_{uid}", password="Test1234", role=User.Role.STUDENT
        )
        self.student = StudentProfile.objects.create(
            school=self.school,
            user=self.student_user,
            first_name="Stu",
            last_name="Dent",
            student_code=f"ES-{uid}",
            academic_year=self.year,
            is_active=True,
        )
        self.staff_user = User.objects.create_user(
            username=f"erase_staff_{uid}", password="Test1234", role=User.Role.TEACHER
        )
        TeacherProfile.objects.create(user=self.staff_user, school=self.school)
        self.guardian_user = User.objects.create_user(
            username=f"erase_guard_{uid}", password="Test1234", role=User.Role.PARENT
        )
        StudentGuardian.objects.create(
            guardian_user=self.guardian_user,
            student=self.student,
            relationship=StudentGuardian.Relationship.GUARDIAN,
        )

    def _client(self) -> Client:
        client = Client(HTTP_HOST=f"{self.school.subdomain}.runmycampus.com")
        client.force_login(self.admin)
        sign_session_school_bind(
            client.session, school_id=str(self.school.pk), user_id=self.admin.pk
        )
        client.session.save()
        return client

    def test_get_erasure_form_renders_subject_kinds(self):
        resp = self._client().get(reverse("compliance:erasure_request"))
        self.assertEqual(resp.status_code, 200)
        body = resp.content.decode("utf-8")
        self.assertIn('name="subject_kind"', body)
        self.assertIn('name="staff_user_id"', body)
        self.assertIn('name="guardian_user_id"', body)

    def test_student_queue_creates_erase_request(self):
        resp = self._client().post(
            reverse("compliance:erasure_request"),
            {"subject_kind": "student", "student_id": str(self.student.pk)},
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            EraseRequest.objects.filter(
                school=self.school, subject_user_id=self.student_user.pk
            ).exists()
        )

    def test_staff_queue_creates_erase_request(self):
        resp = self._client().post(
            reverse("compliance:erasure_request"),
            {"subject_kind": "staff", "staff_user_id": str(self.staff_user.pk)},
        )
        self.assertEqual(resp.status_code, 302)
        er = EraseRequest.objects.filter(
            school=self.school, subject_user_id=self.staff_user.pk
        ).first()
        self.assertIsNotNone(er)
        self.assertIn("staff_user_id", er.reason)

    def test_guardian_queue_creates_erase_request(self):
        resp = self._client().post(
            reverse("compliance:erasure_request"),
            {
                "subject_kind": "guardian",
                "guardian_user_id": str(self.guardian_user.pk),
            },
        )
        self.assertEqual(resp.status_code, 302)
        self.assertTrue(
            EraseRequest.objects.filter(
                school=self.school, subject_user_id=self.guardian_user.pk
            ).exists()
        )
