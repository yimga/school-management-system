"""Structured AI → workflow bridge (no auto-actions)."""

from django.test import TestCase

from apps.platform_runtime.ai_workflow_bridge import build_structured_workflow_suggestions
from apps.schools.models import School


class AiWorkflowBridgeTests(TestCase):
    databases = {"default"}

    def test_structured_payload_requires_approval_flag(self):
        school = School.objects.create(
            name="Bridge School",
            slug="bridge-wf",
            subdomain="bridgewf",
            is_active=True,
        )
        out = build_structured_workflow_suggestions(
            school=school,
            user=None,
            health_snapshot={"risk_tier": "high"},
            onboarding_keys=["step_a"],
            analytics_keys=["k1"],
        )
        self.assertEqual(out.get("schema_version"), 1)
        self.assertTrue(out.get("requires_human_approval"))
        self.assertGreaterEqual(len(out.get("suggestions") or []), 1)
        kinds = {s.get("kind") for s in (out.get("suggestions") or [])}
        self.assertIn("health", kinds)
