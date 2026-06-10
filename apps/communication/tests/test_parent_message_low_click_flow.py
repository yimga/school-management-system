"""Parent message low-click flow."""

from django.test import TestCase

from apps.platform_runtime.tenant_daily_ops import next_best_actions_for_role
from apps.schools.models import School


class ParentMessageLowClickTests(TestCase):
    def test_parent_messages_action(self):
        school = School.objects.create(
            name="Msg School",
            slug="msg-school",
            subdomain="msg-school",
            is_active=True,
        )
        user = type("U", (), {"role": "PARENT"})()
        actions = next_best_actions_for_role(school, user)
        self.assertTrue(any(a["key"] == "messages" for a in actions))
