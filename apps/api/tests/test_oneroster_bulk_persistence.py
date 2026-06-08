from __future__ import annotations

import uuid
from datetime import date

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import User
from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership


@override_settings(RMC_ONEROSTER_ACCESS_TOKEN="bulk-write-token")
class OneRosterBulkPersistenceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Bulk Roster School",
            slug="bulk-roster-school",
            subdomain="bulk-roster-school",
            is_active=True,
        )
        self.url = reverse("api:api-roster-v1p2-users-bulk")
        self.headers = {"HTTP_AUTHORIZATION": "Bearer bulk-write-token"}

    def _post(self, users, key=None):
        return self.client.post(
            self.url,
            data={"users": users},
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=key or uuid.uuid4().hex,
            **self.headers,
        )

    def test_valid_rows_create_users_and_tenant_memberships(self):
        response = self._post(
            [
                {
                    "sourcedId": "student-001",
                    "username": "student.001",
                    "givenName": "Ada",
                    "familyName": "Lovelace",
                    "email": "ada@example.test",
                    "role": "student",
                    "orgSourcedIds": [self.school.slug],
                },
                {
                    "sourcedId": "teacher-001",
                    "username": "teacher.001",
                    "givenName": "Alan",
                    "familyName": "Turing",
                    "role": "teacher",
                    "orgSourcedIds": [str(self.school.pk)],
                },
            ]
        )

        self.assertEqual(response.status_code, 207)
        payload = response.json()
        self.assertEqual(payload["summary"]["created"], 2)
        self.assertEqual(payload["summary"]["error"], 0)
        self.assertEqual(
            [row["status"] for row in payload["results"]],
            ["created", "created"],
        )
        student = User.objects.get(username="student.001")
        teacher = User.objects.get(username="teacher.001")
        self.assertEqual(student.role, User.Role.STUDENT)
        self.assertEqual(teacher.role, User.Role.TEACHER)
        self.assertFalse(student.has_usable_password())
        self.assertTrue(
            SchoolMembership.objects.filter(
                school=self.school,
                user=student,
                role=User.Role.STUDENT,
            ).exists()
        )

    def test_repeat_with_new_idempotency_key_updates_existing_user(self):
        row = {
            "sourcedId": "person-001",
            "username": "person.001",
            "givenName": "Initial",
            "familyName": "Name",
            "role": "student",
            "orgSourcedIds": [self.school.slug],
        }
        first = self._post([row])
        row["givenName"] = "Updated"
        second = self._post([row])

        self.assertEqual(first.json()["results"][0]["status"], "created")
        self.assertEqual(second.json()["results"][0]["status"], "updated")
        self.assertEqual(User.objects.filter(username="person.001").count(), 1)
        self.assertEqual(
            User.objects.get(username="person.001").first_name,
            "Updated",
        )

    def test_idempotency_replay_does_not_apply_twice(self):
        key = uuid.uuid4().hex
        row = {
            "sourcedId": "replay-001",
            "givenName": "Replay",
            "familyName": "User",
            "role": "guardian",
            "orgSourcedIds": [self.school.slug],
        }
        first = self._post([row], key=key)
        second = self._post([row], key=key)

        self.assertEqual(first.status_code, 207)
        self.assertEqual(second.status_code, 207)
        self.assertEqual(second["Idempotency-Replay"], "true")
        self.assertEqual(User.objects.filter(username="replay-001").count(), 1)

    def test_invalid_row_does_not_abort_valid_rows(self):
        response = self._post(
            [
                {
                    "sourcedId": "valid-001",
                    "givenName": "Valid",
                    "familyName": "User",
                    "role": "staff",
                },
                {
                    "sourcedId": "invalid-001",
                    "givenName": "Invalid",
                    "familyName": "User",
                    "role": "unknown-role",
                },
            ]
        )

        self.assertEqual(response.status_code, 207)
        payload = response.json()
        self.assertEqual(payload["summary"]["created"], 1)
        self.assertEqual(payload["summary"]["error"], 1)
        self.assertTrue(User.objects.filter(username="valid-001").exists())

    def test_org_resource_route_accepts_put(self):
        org_url = reverse(
            "api:api-roster-v1p2-org-detail",
            kwargs={"sourced_id": "resource-school"},
        )
        response = self.client.put(
            org_url,
            data={
                "org": {
                    "name": "Resource School",
                    "identifier": "resource-school",
                }
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex,
            **self.headers,
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(School.objects.filter(slug="resource-school").exists())

    def test_classes_bulk_creates_classroom(self):
        AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        url = reverse("api:api-roster-v1p2-classes-bulk")
        response = self.client.post(
            url,
            data={
                "classes": [
                    {
                        "sourcedId": "class-bio-101",
                        "title": "Biology 101",
                        "classCode": "BIO101",
                        "schoolSourcedId": self.school.slug,
                    }
                ]
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex,
            **self.headers,
        )
        self.assertEqual(response.status_code, 207)
        payload = response.json()
        self.assertEqual(payload["summary"]["created"], 1)
        classroom = Classroom.objects.filter(
            school=self.school,
            name="Biology 101",
        ).first()
        self.assertIsNotNone(classroom)
        self.assertTrue(str(classroom.code).endswith("BIO101"))

    def test_enrollments_bulk_binds_student_to_classroom(self):
        year = AcademicYear.objects.create(
            school=self.school,
            name="2025/2026",
            start_date=date(2025, 9, 1),
            end_date=date(2026, 6, 30),
            is_active=True,
        )
        department = Department.objects.create(
            school=self.school,
            code="SCI",
            name="Science",
        )
        classroom = Classroom.objects.create(
            school=self.school,
            academic_year=year,
            department=department,
            name="Biology 101",
            code="BIO101",
        )
        user = User.objects.create_user(
            username="enroll.student",
            password="unused",
            role=User.Role.STUDENT,
        )
        student = StudentProfile.objects.create(
            school=self.school,
            user=user,
            first_name="Enroll",
            last_name="Student",
            student_code="ENR-001",
            academic_year=year,
        )
        url = reverse("api:api-roster-v1p2-enrollments-bulk")
        response = self.client.post(
            url,
            data={
                "enrollments": [
                    {
                        "sourcedId": "enr-001",
                        "role": "student",
                        "userSourcedId": str(user.pk),
                        "classSourcedId": str(classroom.pk),
                    }
                ]
            },
            content_type="application/json",
            HTTP_IDEMPOTENCY_KEY=uuid.uuid4().hex,
            **self.headers,
        )
        self.assertEqual(response.status_code, 207)
        payload = response.json()
        self.assertEqual(payload["summary"]["created"], 1)
        student.refresh_from_db()
        self.assertEqual(student.classroom_id, classroom.pk)
