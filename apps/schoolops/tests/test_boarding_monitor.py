"""Wave D — RFID/NFC/QR bus boarding monitor.

A passive tap records an append-only, idempotent BusBoardingEvent, resolves the
route from the student's standing transport assignment, and flags a best-effort
parent notification.
"""

from __future__ import annotations

import uuid

from django.test import TestCase
from django.utils import timezone

from apps.academics.models import AcademicYear, Classroom, Department
from apps.people.models import StudentProfile
from apps.schoolops.boarding_monitor import record_boarding
from apps.schoolops.models import BusBoardingEvent, Route, TransportAssignment
from apps.schools.models import School


class BusBoardingMonitorTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"BUS {uid}", slug=f"bus-{uid}", subdomain=f"bus{uid}", is_active=True
        )
        year = AcademicYear.objects.create(
            name="Y1", start_date="2025-01-01", end_date="2025-12-31", school=self.school
        )
        dept = Department.objects.create(name="D", code=f"D{uid}", school=self.school)
        classroom = Classroom.objects.create(
            academic_year=year, department=dept, name="C1", code=f"C{uid}", school=self.school
        )
        self.student = StudentProfile.objects.create(
            first_name="S",
            last_name="T",
            date_of_birth="2012-01-01",
            student_code=f"ST{uid}",
            school=self.school,
            classroom=classroom,
        )
        self.route = Route.objects.create(school=self.school, name=f"Route {uid}")

    def test_tap_records_event(self):
        res = record_boarding(
            school_id=self.school.id,
            student=self.student,
            occurred_at=timezone.now(),
            direction="board",
            capture_method="rfid",
            device_id="READER-A",
            notify=False,
        )
        self.assertTrue(res["ok"], res)
        ev = BusBoardingEvent.objects.get(pk=res["boarding_event_id"])
        self.assertEqual(ev.student_id, self.student.pk)
        self.assertEqual(ev.direction, "board")
        self.assertEqual(ev.capture_method, "rfid")

    def test_route_resolved_from_assignment(self):
        TransportAssignment.objects.create(
            school=self.school,
            student=self.student,
            route=self.route,
            effective_from=timezone.localdate(),
        )
        res = record_boarding(
            school_id=self.school.id,
            student=self.student,
            occurred_at=timezone.now(),
            notify=False,
        )
        self.assertEqual(res["route_id"], self.route.id)

    def test_idempotent_per_key(self):
        kwargs = dict(
            school_id=self.school.id,
            student=self.student,
            occurred_at=timezone.now(),
            idempotency_key="tap-xyz-1",
            notify=False,
        )
        r1 = record_boarding(**kwargs)
        r2 = record_boarding(**kwargs)
        self.assertEqual(r1["boarding_event_id"], r2["boarding_event_id"])
        self.assertTrue(r2.get("dedup"))
        self.assertEqual(
            BusBoardingEvent.objects.filter(school_id=self.school.id).count(), 1
        )

    def test_invalid_direction_and_method_normalised(self):
        res = record_boarding(
            school_id=self.school.id,
            student=self.student,
            occurred_at=timezone.now(),
            direction="teleport",
            capture_method="laser",
            notify=False,
        )
        ev = BusBoardingEvent.objects.get(pk=res["boarding_event_id"])
        self.assertEqual(ev.direction, "board")
        self.assertEqual(ev.capture_method, "rfid")

    def test_unknown_student_rejected(self):
        res = record_boarding(
            school_id=self.school.id, student=None, occurred_at=timezone.now()
        )
        self.assertFalse(res["ok"])
