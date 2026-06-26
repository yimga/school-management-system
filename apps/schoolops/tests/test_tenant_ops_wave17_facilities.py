"""Wave 17: facilities / maintenance ops module."""

import uuid

from django.contrib.auth import get_user_model
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory, TestCase

from apps.schoolops.models import MaintenanceRequest
from apps.schoolops.views_tenant_ops import ops_facilities
from apps.schools.models import School

User = get_user_model()


class TenantOpsWave17FacilitiesTests(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.school = School.objects.create(
            name="Fac School",
            slug=f"fac-{uuid.uuid4().hex[:10]}",
            subdomain=f"fac-{uuid.uuid4().hex[:10]}",
            features={"facilities_ops": True},
        )
        self.admin = User.objects.create_user(
            username=f"adm-{uuid.uuid4().hex[:8]}",
            email="a@f.test",
            password="x",
            role=User.Role.ADMIN,
        )

    def _req(self, method, path, data=None):
        if method == "GET":
            r = self.factory.get(path)
        else:
            r = self.factory.post(path, data or {})
        r.user = self.admin
        r.school = self.school
        SessionMiddleware(lambda x: None).process_request(r)
        r.session.save()
        setattr(r, "_messages", FallbackStorage(r))
        return r

    def test_create_and_close_ticket(self):
        r = ops_facilities(
            self._req(
                "POST",
                "/f/",
                {
                    "title": "Leak in lab",
                    "location": "Block B",
                    "description": "Ceiling tile",
                },
            )
        )
        self.assertEqual(r.status_code, 302)
        t = MaintenanceRequest.objects.get(school=self.school)
        self.assertEqual(t.status, MaintenanceRequest.Status.OPEN)
        r2 = ops_facilities(
            self._req(
                "POST",
                "/f/",
                {
                    "action": "set_status",
                    "ticket_id": str(t.pk),
                    "new_status": "closed",
                },
            )
        )
        self.assertEqual(r2.status_code, 302)
        t.refresh_from_db()
        self.assertEqual(t.status, MaintenanceRequest.Status.CLOSED)
        self.assertIsNotNone(t.closed_at)

    def test_create_resource_and_booking(self):
        r = ops_facilities(
            self._req(
                "POST",
                "/f/",
                {
                    "action": "create_resource",
                    "resource_name": "Lab A",
                    "resource_type": "lab",
                    "resource_capacity": "1",
                },
            )
        )
        self.assertEqual(r.status_code, 302)
        from apps.schoolops.models import BookableResource

        resource = BookableResource.objects.get(school=self.school, name="Lab A")
        if connection.vendor != "postgresql":
            self.skipTest("Resource booking insert requires PostgreSQL")
        start = "2026-07-01T09:00"
        end = "2026-07-01T10:00"
        r2 = ops_facilities(
            self._req(
                "POST",
                "/f/",
                {
                    "action": "book_resource",
                    "resource_id": str(resource.pk),
                    "booking_title": "Chem class",
                    "booking_start": start,
                    "booking_end": end,
                },
            )
        )
        self.assertEqual(r2.status_code, 302)
        r3 = ops_facilities(self._req("GET", "/f/"))
        self.assertEqual(r3.status_code, 200)
        self.assertIn(b"Chem class", r3.content)

    def test_facilities_feature_off_403(self):
        self.school.features = {"facilities_ops": False}
        self.school.save(update_fields=["features"])
        resp = ops_facilities(self._req("GET", "/f/"))
        self.assertEqual(resp.status_code, 403)
