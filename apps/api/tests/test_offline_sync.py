"""
Tests for offline sync: sync_batch processes queued attendance (and grade) data.
Simulates "network down then back": when client sends sync_batch with attendance data,
server creates/updates the Attendance record. Used to assert offline-queued writes
are applied correctly when replayed.
"""
import uuid
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import User
from apps.academics.models import (
    AcademicYear,
    Attendance,
    Classroom,
    Department,
)
from apps.api.mobile_api import MobileDevice
from apps.people.models import StudentProfile
from apps.siteconfig.models import SiteSettings


class OfflineSyncBatchTestCase(TestCase):
    """Test that sync_batch applies queued attendance so 'network down then back' results in server state."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="sync_test_user",
            password="testpass123",
            is_staff=True,
        )
        self.client_api = APIClient()
        self.client_api.force_authenticate(user=self.user)

        year = AcademicYear.objects.create(
            name="2024-2025",
            starts_on="2024-01-01",
            ends_on="2024-12-31",
        )
        dept = Department.objects.create(name="Test Dept", code="TD")
        self.classroom = Classroom.objects.create(
            academic_year=year,
            department=dept,
            name="Form 1A",
            code="F1A",
        )
        self.student = StudentProfile.objects.create(
            first_name="Sync",
            last_name="Student",
            date_of_birth="2012-05-01",
        )

        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id=uuid.uuid4(),
            device_name="Test Device",
            platform="WEB",
            app_version="1.0",
        )

        site = SiteSettings.get_solo()
        site.enable_offline_mode = True
        site.save(update_fields=["enable_offline_mode"])
        flags = site.backend_feature_flags or {}
        flags["enable_offline_attendance_sync"] = True
        site.backend_feature_flags = flags
        site.save(update_fields=["backend_feature_flags"])

    def test_sync_batch_attendance_creates_record(self):
        """When sync_batch is called with attendance data (as after 'coming back online'),
        the server creates the Attendance record so offline-queued save is visible."""
        try:
            url = reverse("api:offline-sync-sync_batch")
        except Exception:
            url = "/api/sync/sync_batch/"
        payload = {
            "device_id": str(self.device.device_id),
            "changes": [
                {
                    "entity_type": "attendance",
                    "entity_id": 0,
                    "action": "CREATE",
                    "data": {
                        "student_id": self.student.id,
                        "classroom_id": self.classroom.id,
                        "date": "2024-06-15",
                        "status": Attendance.Status.PRESENT,
                        "remarks": "Synced after offline",
                    },
                    "client_timestamp": timezone.now().isoformat(),
                },
            ],
        }
        response = self.client_api.post(url, payload, format="json")
        self.assertEqual(response.status_code, 200, response.data)
        self.assertEqual(response.data.get("synced"), 1, response.data)
        self.assertEqual(response.data.get("failed", 0), 0, response.data)

        att = Attendance.objects.filter(
            student=self.student,
            classroom=self.classroom,
            date="2024-06-15",
        ).first()
        self.assertIsNotNone(att, "Attendance record should exist after sync_batch")
        self.assertEqual(att.status, Attendance.Status.PRESENT)
        self.assertEqual(att.remarks, "Synced after offline")
