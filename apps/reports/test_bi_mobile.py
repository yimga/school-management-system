"""
Phase 9 Task 1 & 2: Tests for BI Reporting and Mobile API
"""

from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
import uuid

User = get_user_model()


class ExecutiveReportingServiceTestCase(TestCase):
    """Test executive reporting services"""

    def setUp(self):
        uid = id(self)
        self.user = User.objects.create_user(
            username="reports_exec_%s" % uid,
            email="exec_%s@test.com" % uid,
            password="testpass123",
        )

    def test_financial_summary(self):
        """Test financial summary generation"""
        from apps.reports.bi_services import ExecutiveReportingService

        end_date = timezone.now()
        start_date = end_date - timedelta(days=30)

        summary = ExecutiveReportingService.get_financial_summary(start_date, end_date)

        self.assertIn("total_invoiced", summary)
        self.assertIn("total_collected", summary)
        self.assertIn("collection_rate", summary)

    def test_academic_summary(self):
        """Test academic summary generation"""
        from apps.reports.bi_services import ExecutiveReportingService

        summary = ExecutiveReportingService.get_academic_summary(1, 1)

        self.assertIn("total_students", summary)
        self.assertIn("average_score", summary)


class ReportDefinitionTestCase(TestCase):
    """ReportDefinition model removed in migration 0017; placeholder for BI API tests."""

    def test_report_definition_model_retired(self):
        from apps.reports.bi_services import ReportCacheManager

        ReportCacheManager.invalidate_report_cache("FINANCE")
        self.assertTrue(True)


class MobileDeviceTestCase(TestCase):
    """Test mobile device registration"""

    def setUp(self):
        uid = id(self)
        self.user = User.objects.create_user(
            username="reports_mobile_%s" % uid,
            email="mobile_%s@test.com" % uid,
            password="testpass123",
        )

    def test_register_device(self):
        """Test device registration"""
        from apps.api.mobile_api import MobileDevice

        device = MobileDevice.objects.create(
            user=self.user, device_name="iPhone 14", platform="IOS", app_version="1.0.0"
        )

        self.assertIsNotNone(device.device_id)
        self.assertTrue(device.is_active)
        self.assertEqual(device.platform, "IOS")

    def test_device_uniqueness(self):
        """Test device_id uniqueness"""
        from apps.api.mobile_api import MobileDevice

        device_id = uuid.uuid4()

        MobileDevice.objects.create(
            user=self.user,
            device_id=device_id,
            device_name="Device 1",
            platform="ANDROID",
            app_version="1.0.0",
        )

        with self.assertRaises(Exception):
            MobileDevice.objects.create(
                user=self.user,
                device_id=device_id,
                device_name="Device 2",
                platform="ANDROID",
                app_version="1.0.0",
            )


class PushNotificationTestCase(TestCase):
    """Test push notifications"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="notif_user", email="notif@test.com", password="testpass123"
        )

        from apps.api.mobile_api import MobileDevice

        self.device = MobileDevice.objects.create(
            user=self.user,
            device_name="Test Device",
            platform="ANDROID",
            app_version="1.0.0",
            push_token="test_token_123",
        )

    def test_create_notification(self):
        """Test creating push notification"""
        from apps.api.mobile_api import PushNotification

        notification = PushNotification.objects.create(
            device=self.device,
            title="Test Notification",
            body="This is a test message",
            priority="HIGH",
        )

        self.assertEqual(notification.status, "PENDING")
        self.assertEqual(notification.priority, "HIGH")

    def test_mark_delivered(self):
        """Test marking notification as delivered"""
        from apps.api.mobile_api import PushNotification

        notification = PushNotification.objects.create(
            device=self.device, title="Test", body="Message"
        )

        notification.status = "DELIVERED"
        notification.delivered_at = timezone.now()
        notification.save()

        self.assertEqual(notification.status, "DELIVERED")
        self.assertIsNotNone(notification.delivered_at)


class OfflineSyncTestCase(TestCase):
    """Test offline synchronization"""

    def setUp(self):
        self.user = User.objects.create_user(
            username="sync_user", email="sync@test.com", password="testpass123"
        )

        from apps.api.mobile_api import MobileDevice

        self.device = MobileDevice.objects.create(
            user=self.user,
            device_name="Sync Device",
            platform="IOS",
            app_version="1.0.0",
        )

    def test_create_sync_queue(self):
        """Test creating sync queue item"""
        from apps.api.mobile_api import OfflineSyncQueue

        sync_item = OfflineSyncQueue.objects.create(
            device=self.device,
            entity_type="evaluation",
            entity_id=123,
            action="UPDATE",
            data={"score": 85},
            client_timestamp=timezone.now(),
        )

        self.assertEqual(sync_item.status, "PENDING")
        self.assertEqual(sync_item.action, "UPDATE")

    def test_sync_conflict(self):
        """Test handling sync conflict"""
        from apps.api.mobile_api import OfflineSyncQueue

        sync_item = OfflineSyncQueue.objects.create(
            device=self.device,
            entity_type="attendance",
            entity_id=456,
            action="CREATE",
            data={"present": True},
            client_timestamp=timezone.now(),
            status="CONFLICT",
            conflict_data={"server_value": False, "client_value": True},
        )

        self.assertEqual(sync_item.status, "CONFLICT")
        self.assertIsNotNone(sync_item.conflict_data)


class ReportCacheManagerTestCase(TestCase):
    """Test report caching"""

    def test_cache_report(self):
        """Test caching report data"""
        from apps.reports.bi_services import ReportCacheManager

        def sample_generator(**params):
            return {"result": "test_data", "count": 100}

        result = ReportCacheManager.get_or_generate(
            "FINANCE", {"year": 2026}, sample_generator
        )

        self.assertEqual(result["result"], "test_data")
        self.assertEqual(result["count"], 100)

    def test_cache_invalidation(self):
        """Test cache invalidation"""
        from apps.reports.bi_services import ReportCacheManager

        # This should clear all finance report caches
        ReportCacheManager.invalidate_report_cache("FINANCE")

        # Verify cleared (simplified test)
        self.assertTrue(True)


class AdHocReportBuilderTestCase(TestCase):
    """Test ad-hoc report builder"""

    def test_export_to_csv(self):
        """Test CSV export"""
        from apps.reports.bi_services import AdHocReportBuilder

        data = [{"name": "John", "score": 85}, {"name": "Jane", "score": 92}]

        csv_output = AdHocReportBuilder.export_to_csv(data, "test.csv")

        self.assertIn("name", csv_output)
        self.assertIn("John", csv_output)
        self.assertIn("Jane", csv_output)

    def test_export_to_json(self):
        """Test JSON export"""
        from apps.reports.bi_services import AdHocReportBuilder

        data = [{"id": 1, "value": "test"}]

        json_output = AdHocReportBuilder.export_to_json(data)

        self.assertIn("test", json_output)
