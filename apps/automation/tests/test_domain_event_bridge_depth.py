"""Salesforce pillar: domain event chain depth guard."""

from unittest.mock import MagicMock, patch

from django.test import TestCase

from apps.automation.domain_event_bridge import dispatch_domain_event_to_triggers
from apps.automation.workflow_limits import MAX_DOMAIN_EVENT_CHAIN_DEPTH
from apps.schools.models import School


class DomainEventBridgeDepthTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Bridge School",
            slug="bridge-school",
            subdomain="bridge-school",
            is_active=True,
        )

    def test_depth_limit_blocks_dispatch(self):
        event = MagicMock()
        event.event_type = "payment_success"
        event.school_id = self.school.pk
        event.payload = {"_domain_event_depth": MAX_DOMAIN_EVENT_CHAIN_DEPTH + 1}

        with patch("apps.automation.domain_event_bridge.fire") as fire_mock:
            result = dispatch_domain_event_to_triggers(event)
        self.assertEqual(result, [])
        fire_mock.assert_not_called()

    def test_depth_increments_on_dispatch(self):
        event = MagicMock()
        event.event_type = "payment_success"
        event.school_id = self.school.pk
        event.pk = 99
        event.payload = {"_domain_event_depth": 0}

        with patch("apps.automation.domain_event_bridge.fire") as fire_mock:
            fire_mock.return_value = []
            dispatch_domain_event_to_triggers(event)

        ctx = fire_mock.call_args[0][1]
        self.assertEqual(ctx["_domain_event_depth"], 1)
