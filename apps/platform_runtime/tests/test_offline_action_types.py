from django.test import SimpleTestCase

from apps.platform_runtime.offline_action_types import (
    OfflineActionType,
    is_notify_action,
    validate_offline_payload,
)


class OfflineActionTypesTests(SimpleTestCase):
    def test_notify_parent_valid(self):
        errors = validate_offline_payload(
            OfflineActionType.NOTIFY_PARENT,
            {
                "template_key": "low_meal_balance",
                "recipient_user_id": "42",
                "context": {"locale": "fr"},
            },
        )
        self.assertEqual(errors, [])

    def test_forbidden_smtp_keys(self):
        errors = validate_offline_payload(
            OfflineActionType.NOTIFY_PARENT,
            {"template_key": "low_meal_balance", "smtp_password": "x"},
        )
        self.assertTrue(any("forbidden" in e for e in errors))

    def test_is_notify_action(self):
        self.assertTrue(is_notify_action("notify.parent"))
