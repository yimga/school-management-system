"""
Tests for offline sync: sync_batch processes queued attendance (and grade) data.
Simulates "network down then back": when client sends sync_batch with attendance data,
server creates/updates the Attendance record. Used to assert offline-queued writes
are applied correctly when replayed.
"""

import uuid
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.urls.exceptions import NoReverseMatch
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
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.finance.models import (
    ComplianceProfile,
    Invoice,
    OfflinePaymentIntent,
    PaymentMethodCode,
)


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

        site = get_platform_site_settings_record(create=True)
        bff = dict(site.get_backend_feature_flags())
        bff["enable_offline_attendance_sync"] = True
        site.apply_feature_control_state(
            backend_feature_flags=bff,
            field_updates={"enable_offline_mode": True},
        )

    def test_sync_batch_attendance_creates_record(self):
        """When sync_batch is called with attendance data (as after 'coming back online'),
        the server creates the Attendance record so offline-queued save is visible."""
        try:
            url = reverse("api:offline-sync-sync-batch")
        except NoReverseMatch:
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


class OfflinePaymentSyncBatchTests(TestCase):
    """sync_batch accepts queued offline payment payloads (edge / no gateway)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="pay_sync_user",
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
        self.profile = ComplianceProfile.objects.create(
            name="CM Test",
            country_code="CM",
            currency_code="XAF",
            currency_symbol="FCFA",
        )
        self.student = StudentProfile.objects.create(
            first_name="Pay",
            last_name="Student",
            date_of_birth="2012-05-01",
        )
        self.invoice = Invoice.objects.create(
            profile=self.profile,
            academic_year=year,
            invoice_type=Invoice.InvoiceType.AR,
            status=Invoice.Status.ISSUED,
            student=self.student,
            total_amount=Decimal("100.00"),
            balance_amount=Decimal("100.00"),
            issued_date="2024-06-01",
        )
        self.device = MobileDevice.objects.create(
            user=self.user,
            device_id=uuid.uuid4(),
            device_name="Pay Device",
            platform="WEB",
            app_version="1.0",
        )
        site = get_platform_site_settings_record(create=True)
        bff = dict(site.get_backend_feature_flags())
        bff["enable_offline_attendance_sync"] = True
        bff["enable_offline_payment_sync"] = True
        site.apply_feature_control_state(
            backend_feature_flags=bff,
            field_updates={"enable_offline_mode": True},
        )

    def test_sync_batch_offline_payment_creates_intent(self):
        try:
            url = reverse("api:offline-sync-sync-batch")
        except NoReverseMatch:
            url = "/api/sync/sync_batch/"
        payload = {
            "device_id": str(self.device.device_id),
            "changes": [
                {
                    "entity_type": "offline_payment",
                    "entity_id": 0,
                    "action": "CREATE",
                    "data": {
                        "invoice_id": self.invoice.id,
                        "amount": "50.00",
                        "payment_method": PaymentMethodCode.CASH,
                        "client_offline_id": "pay-offline-1",
                        "notes": "Cash collected during outage",
                    },
                    "client_timestamp": timezone.now().isoformat(),
                },
            ],
        }
        response = self.client_api.post(url, payload, format="json")
        self.assertEqual(response.status_code, 200, getattr(response, "data", None))
        self.assertEqual(response.data.get("synced"), 1)
        intent = OfflinePaymentIntent.objects.get(invoice=self.invoice)
        self.assertEqual(intent.amount, Decimal("50.00"))
        self.assertEqual(intent.payment_method, PaymentMethodCode.CASH)


class OfflineQueueEncryptionKeyAPITestCase(TestCase):
    """Session-scoped queue encryption key for SW AES-GCM at rest (batch 1651)."""

    def setUp(self):
        self.user = User.objects.create_user(
            username="queue_enc_user",
            password="testpass123",
        )
        site = get_platform_site_settings_record(create=True)
        bff = dict(site.get_backend_feature_flags())
        bff["enable_offline_queue_encryption"] = True
        site.apply_feature_control_state(
            backend_feature_flags=bff,
            field_updates={"enable_offline_mode": True},
        )

    def test_encryption_key_requires_session(self):
        self.client.force_login(self.user)
        url = reverse("api:offline-encryption-key")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("key_b64", data)
        self.assertTrue(len(data["key_b64"]) >= 40)

    def test_encryption_key_disabled_when_flag_off(self):
        site = get_platform_site_settings_record(create=True)
        bff = dict(site.get_backend_feature_flags())
        bff["enable_offline_queue_encryption"] = False
        site.apply_feature_control_state(backend_feature_flags=bff, field_updates={})
        self.client.force_login(self.user)
        url = reverse("api:offline-encryption-key")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 403)
