"""Operator copilot rail service (batch 1393)."""

from django.test import RequestFactory, SimpleTestCase

from apps.observability.ai_copilot_service import (
    build_copilot_rail_payload,
    enrich_manager_copilot_rail,
)


class AICopilotServiceTests(SimpleTestCase):
    def test_stub_when_not_manager_staff(self):
        payload = build_copilot_rail_payload(request=None)
        self.assertFalse(payload["enabled"])
        self.assertEqual(payload.get("deferred_marker"), "")

    def test_enrich_shape(self):
        payload = enrich_manager_copilot_rail(request=None)
        self.assertTrue(payload["enabled"])
        self.assertIn("insight_text", payload)
        self.assertIsInstance(payload.get("suggestions"), list)

    def test_manager_staff_enriched(self):
        rf = RequestFactory()
        request = rf.get("/help-center/")
        request.public_host_kind = "manager"
        request.user = type(
            "U",
            (),
            {"is_authenticated": True, "is_staff": True, "is_superuser": False},
        )()
        payload = build_copilot_rail_payload(request=request)
        self.assertTrue(payload["enabled"])
        self.assertNotEqual(payload.get("deferred_marker"), "v3.57-honest-stub")
