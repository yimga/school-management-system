"""Salesforce pillar: domain events dispatch at most once per pk."""

from unittest.mock import MagicMock, patch

from django.core.cache import cache
from django.test import TestCase

from apps.automation.domain_event_bridge import dispatch_domain_event_to_triggers
from apps.schools.models import School


class DomainEventDedupTests(TestCase):
    def setUp(self):
        cache.clear()
        self.school = School.objects.create(
            name="Dedup School",
            slug="dedup-school",
            subdomain="dedup-school",
            is_active=True,
        )

    def test_second_dispatch_with_same_pk_is_noop(self):
        event = MagicMock()
        event.event_type = "payment_success"
        event.school_id = self.school.pk
        event.pk = 4242
        event.payload = {"_domain_event_depth": 0}

        with patch("apps.automation.domain_event_bridge.fire") as fire_mock:
            fire_mock.return_value = []
            first = dispatch_domain_event_to_triggers(event)
            second = dispatch_domain_event_to_triggers(event)

        self.assertEqual(first, [])
        self.assertEqual(second, [])
        fire_mock.assert_called_once()
