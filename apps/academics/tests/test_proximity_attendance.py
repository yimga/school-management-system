"""Wave B — proximity attendance ingest (ambient capture).

A device-agnostic proximity ping queues an offline ATTENDANCE action that drains
into a real ``academics.Attendance`` row, carrying a proximity audit remark, and
is idempotent per device+student+date.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
)
from apps.academics.proximity_attendance import (
    build_proximity_remarks,
    normalize_capture_method,
    record_proximity_checkin,
)
from apps.accounts.models import User
from apps.people.models import StudentProfile
from apps.platform_runtime.models import OfflineAction
from apps.platform_runtime.offline_queue import process_offline_queue
from apps.schools.models import School


class ProximityAttendancePureTests(TestCase):
    def test_capture_method_normalisation(self):
        self.assertEqual(normalize_capture_method("RFID"), "rfid")
        self.assertEqual(normalize_capture_method("  Beacon "), "beacon")
        self.assertEqual(normalize_capture_method("laser"), "beacon")  # unknown -> default
        self.assertEqual(normalize_capture_method(None), "beacon")

    def test_remarks_include_device_and_rssi(self):
        note = build_proximity_remarks("beacon", "GATE-01", -55)
        self.assertIn("via beacon", note)
        self.assertIn("device GATE-01", note)
        self.assertIn("rssi=-55", note)

    def test_remarks_omit_blank_device_and_rssi(self):
        note = build_proximity_remarks("qr", "", None)
        self.assertEqual(note, "Proximity check-in via qr")


class ProximityAttendanceQueueTests(TestCase):
    databases = {"default"}

    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"PRX {uid}", slug=f"prx-{uid}", subdomain=f"prx{uid}", is_active=True
        )
        self.user = User.objects.create_user(username=f"prx_{uid}", password="x")
        self.year = AcademicYear.objects.create(
            name="Y1", start_date="2025-01-01", end_date="2025-12-31", school=self.school
        )
        dept = Department.objects.create(name="D", code=f"D{uid}", school=self.school)
        self.classroom = Classroom.objects.create(
            academic_year=self.year,
            department=dept,
            name="C1",
            code=f"C{uid}",
            school=self.school,
        )
        self.student = StudentProfile.objects.create(
            first_name="S",
            last_name="T",
            date_of_birth="2012-01-01",
            student_code=f"ST{uid}",
            school=self.school,
            classroom=self.classroom,
        )

    def _checkin(self, **overrides):
        kwargs = dict(
            school_id=self.school.pk,
            user_id=self.user.pk,
            student_id=self.student.pk,
            classroom_id=self.classroom.pk,
            date="2025-09-03",
            capture_method="beacon",
            device_id="GATE-01",
        )
        kwargs.update(overrides)
        return record_proximity_checkin(**kwargs)

    def test_ping_enqueues_attendance_action(self):
        action = self._checkin()
        self.assertEqual(action.action_type, OfflineAction.ActionType.ATTENDANCE)
        self.assertEqual(action.status, OfflineAction.Status.QUEUED)
        self.assertEqual(action.payload["capture_method"], "beacon")
        self.assertEqual(action.payload["status"], "present")
        self.assertIn("Proximity check-in via beacon", action.payload["remarks"])

    def test_queue_drains_into_real_attendance_row(self):
        action = self._checkin(signal_strength=-60)
        process_offline_queue(school_id=self.school.pk, user_id=self.user.pk)
        action.refresh_from_db()
        self.assertEqual(action.status, OfflineAction.Status.SYNCED)
        att = Attendance.objects.get(
            student_id=self.student.pk,
            classroom_id=self.classroom.pk,
            date="2025-09-03",
        )
        self.assertEqual(att.status, "present")
        self.assertIn("via beacon", att.remarks)
        self.assertIn("device GATE-01", att.remarks)

    def test_idempotent_per_device_student_date(self):
        a1 = self._checkin()
        a2 = self._checkin()  # same device+student+date -> dedupes to one row
        self.assertEqual(a1.pk, a2.pk)
        self.assertEqual(
            OfflineAction.objects.filter(
                school_id=self.school.pk,
                action_type=OfflineAction.ActionType.ATTENDANCE,
            ).count(),
            1,
        )
