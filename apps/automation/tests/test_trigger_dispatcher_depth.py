"""Salesforce pillar: trigger_dispatcher honors domain-event depth."""

from django.test import SimpleTestCase

from apps.automation.trigger_dispatcher import fire
from apps.automation.workflow_limits import MAX_DOMAIN_EVENT_CHAIN_DEPTH


class TriggerDispatcherDepthTests(SimpleTestCase):
    def test_depth_above_limit_returns_recursion_error(self):
        results = fire(
            "payment_success",
            {"_domain_event_depth": MAX_DOMAIN_EVENT_CHAIN_DEPTH + 1},
        )
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["error"], "workflow_recursion_limit")
