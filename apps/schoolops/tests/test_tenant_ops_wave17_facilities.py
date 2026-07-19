"""Wave 17: facilities / maintenance ops module."""

import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.schoolops.models import BookableResource, Hostel, HostelRoom, MaintenanceRequest
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

    def test_booking_conflict_surfaces_message(self):
        ops_facilities(
            self._req(
                "POST",
                "/f/",
                {
                    "action": "create_resource",
                    "resource_name": "Gym",
                    "resource_type": "hall",
                    "resource_capacity": "1",
                },
            )
        )
        resource = BookableResource.objects.get(school=self.school, name="Gym")
        if connection.vendor != "postgresql":
            self.skipTest("Resource booking insert requires PostgreSQL")
        start = "2026-07-02T09:00"
        end = "2026-07-02T10:00"
        payload = {
            "action": "book_resource",
            "resource_id": str(resource.pk),
            "booking_title": "PE",
            "booking_start": start,
            "booking_end": end,
        }
        self.assertEqual(ops_facilities(self._req("POST", "/f/", payload)).status_code, 302)
        conflict_req = self._req("POST", "/f/", {**payload, "booking_title": "Overlap"})
        self.assertEqual(ops_facilities(conflict_req).status_code, 302)
        texts = [str(m) for m in get_messages(conflict_req)]
        self.assertTrue(
            any("conflicts with an existing booking" in t for t in texts),
            texts,
        )

    def _seed_confirmed_booking(self, resource, start, end, title):
        """Raw-insert CONFIRMED booking so conflict UX can be proven on SQLite."""
        start = start if timezone.is_aware(start) else timezone.make_aware(start)
        end = end if timezone.is_aware(end) else timezone.make_aware(end)
        time_range = f"[{start.isoformat()},{end.isoformat()})"
        now = timezone.now().isoformat()
        exclusive = resource.capacity == 1
        with connection.cursor() as cur:
            cur.execute(
                "INSERT INTO schoolops_resourcebooking "
                "(school_id, resource_id, title, time_range, status, "
                "enforce_exclusive, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                [
                    self.school.id.hex,
                    resource.id,
                    title,
                    time_range,
                    "confirmed",
                    exclusive,
                    now,
                    now,
                ],
            )

    def test_booking_conflict_surfaces_message_sqlite(self):
        """Service gate → conflict message without Postgres DateTimeRange write."""
        ops_facilities(
            self._req(
                "POST",
                "/f/",
                {
                    "action": "create_resource",
                    "resource_name": "Studio",
                    "resource_type": "hall",
                    "resource_capacity": "1",
                },
            )
        )
        resource = BookableResource.objects.get(school=self.school, name="Studio")
        base = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=3)
        self._seed_confirmed_booking(resource, base, base + timedelta(hours=1), "Seeded")
        start = base.strftime("%Y-%m-%dT%H:%M")
        end = (base + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        conflict_req = self._req(
            "POST",
            "/f/",
            {
                "action": "book_resource",
                "resource_id": str(resource.pk),
                "booking_title": "Overlap",
                "booking_start": start,
                "booking_end": end,
            },
        )
        self.assertEqual(ops_facilities(conflict_req).status_code, 302)
        texts = [str(m) for m in get_messages(conflict_req)]
        self.assertTrue(
            any("conflicts with an existing booking" in t for t in texts),
            texts,
        )

    def test_capacity_two_third_booking_surfaces_conflict_sqlite(self):
        ops_facilities(
            self._req(
                "POST",
                "/f/",
                {
                    "action": "create_resource",
                    "resource_name": "Shared Lab",
                    "resource_type": "lab",
                    "resource_capacity": "2",
                },
            )
        )
        resource = BookableResource.objects.get(school=self.school, name="Shared Lab")
        base = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=4)
        self._seed_confirmed_booking(resource, base, base + timedelta(hours=1), "A")
        self._seed_confirmed_booking(resource, base, base + timedelta(hours=1), "B")
        start = base.strftime("%Y-%m-%dT%H:%M")
        end = (base + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M")
        conflict_req = self._req(
            "POST",
            "/f/",
            {
                "action": "book_resource",
                "resource_id": str(resource.pk),
                "booking_title": "C",
                "booking_start": start,
                "booking_end": end,
            },
        )
        self.assertEqual(ops_facilities(conflict_req).status_code, 302)
        texts = [str(m) for m in get_messages(conflict_req)]
        self.assertTrue(
            any("conflicts with an existing booking" in t for t in texts),
            texts,
        )

    def test_create_resource_links_hostel_room(self):
        hostel = Hostel.objects.create(school=self.school, name="East Dorm", capacity=20)
        room = HostelRoom.objects.create(hostel=hostel, name="E-12", capacity=4)
        resp = ops_facilities(
            self._req(
                "POST",
                "/f/",
                {
                    "action": "create_resource",
                    "resource_name": "East Dorm E-12",
                    "resource_type": "room",
                    "hostel_room_id": str(room.pk),
                },
            )
        )
        self.assertEqual(resp.status_code, 302)
        resource = BookableResource.objects.get(
            school=self.school, name="East Dorm E-12"
        )
        self.assertEqual(resource.hostel_room_id, room.pk)
        self.assertEqual(resource.capacity, 4)

    def test_create_resource_rejects_foreign_hostel_room(self):
        other = School.objects.create(
            name="Other Fac",
            slug=f"fac-o-{uuid.uuid4().hex[:8]}",
            subdomain=f"fac-o-{uuid.uuid4().hex[:8]}",
            features={"facilities_ops": True},
        )
        hostel = Hostel.objects.create(school=other, name="Away", capacity=10)
        room = HostelRoom.objects.create(hostel=hostel, name="A-1", capacity=2)
        before = BookableResource.objects.filter(school=self.school).count()
        req = self._req(
            "POST",
            "/f/",
            {
                "action": "create_resource",
                "resource_name": "Should Fail",
                "resource_type": "room",
                "hostel_room_id": str(room.pk),
                "resource_capacity": "2",
            },
        )
        self.assertEqual(ops_facilities(req).status_code, 302)
        texts = [str(m) for m in get_messages(req)]
        self.assertTrue(
            any("hostel room from this school" in t for t in texts),
            texts,
        )
        self.assertEqual(
            BookableResource.objects.filter(school=self.school).count(),
            before,
        )

    def test_facilities_feature_off_403(self):
        self.school.features = {"facilities_ops": False}
        self.school.save(update_fields=["features"])
        resp = ops_facilities(self._req("GET", "/f/"))
        self.assertEqual(resp.status_code, 403)
