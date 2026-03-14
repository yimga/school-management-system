from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.automation.models import AutomationExecutionLog
from apps.finance.models import Notification
from apps.platform_runtime.helpers import get_platform_site_settings_record
from apps.requests.models import AccessRequest
from apps.requests.tasks import remind_pending_assignees_task


User = get_user_model()


class RequestsReminderTaskTests(TestCase):
    def setUp(self):
        self.assignee = User.objects.create_user(
            username="assignee-user",
            email="assignee@example.com",
            password="password",
            is_active=True,
        )
        self.requester = User.objects.create_user(
            username="requester-user",
            email="requester@example.com",
            password="password",
            is_active=True,
        )
        AccessRequest.objects.create(
            request_type=AccessRequest.RequestType.MODULE_ACCESS,
            status=AccessRequest.Status.PENDING,
            title="Need module access",
            requester=self.requester,
            assigned_to=self.assignee,
        )

    def test_task_creates_success_execution_log_when_enabled(self):
        settings = get_platform_site_settings_record(create=True)
        settings.requests_reminder_interval_hours = 24
        settings.save(update_fields=["requests_reminder_interval_hours"])

        result = remind_pending_assignees_task()

        self.assertEqual(result["notified"], 1)
        self.assertEqual(Notification.objects.count(), 1)
        log = AutomationExecutionLog.objects.filter(
            task_name="requests.remind_pending_assignees"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.SUCCESS)
        self.assertEqual(log.records_processed, 1)
        self.assertEqual(log.execution_summary.get("pending_total"), 1)

    def test_task_logs_success_with_zero_when_disabled(self):
        settings = get_platform_site_settings_record(create=True)
        settings.requests_reminder_interval_hours = 0
        settings.save(update_fields=["requests_reminder_interval_hours"])

        result = remind_pending_assignees_task()

        self.assertEqual(result["notified"], 0)
        log = AutomationExecutionLog.objects.filter(
            task_name="requests.remind_pending_assignees"
        ).latest("started_at")
        self.assertEqual(log.status, AutomationExecutionLog.Status.SUCCESS)
        self.assertEqual(log.records_processed, 0)
