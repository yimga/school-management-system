"""Year-end parent notification contract."""

from django.test import SimpleTestCase


class YearEndParentNotificationContractTests(SimpleTestCase):
    def test_unified_notification_service_importable(self):
        from apps.communication.notification_service import UnifiedNotificationService

        self.assertTrue(hasattr(UnifiedNotificationService, "send_email"))
