from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.schoolops.notification_intent import dispatch_notification_intent
from apps.schools.models import School, SchoolMembership


class NotificationIntentTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.school = School.objects.create(name="Notify School", slug="notify-school")
        self.parent = User.objects.create_user(
            username="parent_notify",
            email="parent@example.com",
            password="Test1234!",
        )
        SchoolMembership.objects.create(
            school=self.school,
            user=self.parent,
            role="PARENT",
        )

    @patch("apps.schoolops.email_delivery.send_transactional")
    def test_dispatch_resolves_recipient(self, mock_send):
        mock_send.return_value = {"ok": True, "attempts": 1}
        result = dispatch_notification_intent(
            school=self.school,
            action_type="notify.parent",
            payload={
                "template_key": "low_meal_balance",
                "recipient_user_id": str(self.parent.pk),
            },
            async_send=False,
        )
        self.assertTrue(result.get("ok"))
        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["to"], "parent@example.com")
