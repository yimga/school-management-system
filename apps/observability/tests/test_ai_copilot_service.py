"""Operator copilot rail service (batch 1393)."""

from django.test import SimpleTestCase

from apps.observability.ai_copilot_service import enrich_manager_copilot_rail


class AICopilotServiceTests(SimpleTestCase):
    def test_enrich_shape(self):
        payload = enrich_manager_copilot_rail(request=None)
        self.assertTrue(payload["enabled"])
        self.assertIn("insight_text", payload)
        self.assertIsInstance(payload.get("suggestions"), list)
