"""HTTP tests for tenant operational health JSON + SSE endpoints."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from apps.schools.models import School, SchoolMembership

User = get_user_model()


class TenantHealthApiHttpTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.school = School.objects.create(
            name="Tenant Health API School",
            slug="tenant-health-api-school",
            subdomain="tenant-health-api-school",
            is_active=True,
            is_approved=True,
        )
        self.admin = User.objects.create_user(
            username="tenant-health-admin",
            password="Test1234!",
            role=User.Role.ADMIN,
        )
        self.parent = User.objects.create_user(
            username="tenant-health-parent",
            password="Test1234!",
            role=User.Role.PARENT,
        )
        self.student = User.objects.create_user(
            username="tenant-health-student",
            password="Test1234!",
            role=User.Role.STUDENT,
        )
        for user in (self.admin, self.parent, self.student):
            SchoolMembership.objects.create(
                user=user,
                school=self.school,
                role=user.role,
                is_primary=True,
            )

    def _bind_school_session(self, user):
        self.client.force_login(user)
        session = self.client.session
        session["school_id"] = str(self.school.id)
        session.save()

    def test_backend_health_json_requires_login(self):
        url = reverse("accounts:backend_operational_health_json")
        anon = self.client.get(url)
        self.assertEqual(anon.status_code, 302)
        self._bind_school_session(self.admin)
        response = self.client.get(url, {"surface": "admin"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("tier", payload)
        self.assertIn("revision", payload)

    def test_portal_health_json_authenticated(self):
        url = reverse("portal:portal_operational_health_json")
        self._bind_school_session(self.parent)
        response = self.client.get(url, {"surface": "parent"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("signals", payload)

    def test_portal_health_json_student_surface(self):
        url = reverse("portal:portal_operational_health_json")
        self._bind_school_session(self.student)
        response = self.client.get(url, {"surface": "student"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload.get("tier"), "degraded")
        self.assertTrue(any(sig.get("key") == "student_profile" for sig in payload.get("signals", [])))

    def test_tenant_health_stream_returns_event_stream(self):
        url = reverse("portal:portal_operational_health_stream")
        self._bind_school_session(self.parent)
        response = self.client.get(url, {"surface": "parent"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response["Content-Type"])

    def test_backend_health_stream_returns_event_stream(self):
        url = reverse("accounts:backend_operational_health_stream")
        self._bind_school_session(self.admin)
        response = self.client.get(url, {"surface": "teacher"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("text/event-stream", response["Content-Type"])
