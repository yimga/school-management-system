"""AI system layer — rules path when disabled; structured output; no network when off."""

from __future__ import annotations

import os
import uuid
from unittest import mock

from django.test import TestCase

from apps.accounts.models import User
from apps.platform_runtime.ai_providers import run_ai_prompt
from apps.platform_runtime.ai_system_layer import (
    generate_anomaly_risk_nudge,
    generate_school_health_insight,
    generate_workflow_suggestion,
    list_ai_recommendation_keys,
    structure_ai_recommendation,
)
from apps.platform_runtime.ai_workflow_bridge import build_ai_approval_handoff
from apps.schools.models import School


class AiSystemLayerUnitTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.school = School.objects.create(
            name="AIL",
            slug=f"ail-{uuid.uuid4().hex[:8]}",
            subdomain=f"ail-{uuid.uuid4().hex[:8]}",
            is_active=True,
        )
        self.user = User.objects.create_user(
            username=f"u_{uuid.uuid4().hex[:8]}",
            password="x" * 8,
        )

    def test_disabled_mode_uses_rules_and_requires_approval(self):
        prev = os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
        try:
            out = generate_school_health_insight(self.school, self.user)
            self.assertEqual(out.get("requires_approval"), True)
            self.assertIn("recommendation_key", out)
            self.assertIn("explanation", out)
            extra = out.get("extra") or {}
            self.assertEqual(extra.get("source"), "rules")
        finally:
            if prev is not None:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    def test_structure_ai_recommendation_validates(self):
        r = structure_ai_recommendation(
            recommendation_key="k",
            title="t",
            explanation="e",
            confidence=2.0,
            proposed_action="a",
        )
        self.assertEqual(r["confidence"], 1.0)
        self.assertTrue(r["requires_approval"])

    def test_workflow_suggestion_rules_when_disabled(self):
        prev = os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
        try:
            w = generate_workflow_suggestion(self.school, self.user, "x")
            self.assertIn("workflow", w.get("recommendation_key", ""))
        finally:
            if prev is not None:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    def test_disabled_prompt_path_never_calls_gateway(self):
        prev = os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
        try:
            with mock.patch("services.ai_gateway.invoke", side_effect=AssertionError("must not invoke")):
                text, meta = run_ai_prompt(
                    "prompt",
                    "ctx",
                    self.school,
                    user=self.user,
                    prompt_type="unit_test",
                )
            self.assertIn("disabled", text.lower())
            self.assertEqual(meta.get("provider"), "disabled")
        finally:
            if prev is not None:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    def test_ai_registry_contains_expected_keys(self):
        keys = list_ai_recommendation_keys()
        self.assertIn("school_health", keys)
        self.assertIn("onboarding_next_action", keys)
        self.assertIn("workflow_hygiene", keys)
        self.assertIn("anomaly_risk", keys)

    def test_anomaly_nudge_rules_path_when_ai_off(self):
        prev = os.environ.pop("RUNMYCAMPUS_AI_ENABLED", None)
        try:
            nudge = generate_anomaly_risk_nudge(self.school, self.user)
            self.assertIsNotNone(nudge)
            self.assertEqual(nudge.get("requires_approval"), True)
            self.assertIn("anomaly", (nudge.get("recommendation_key") or ""))
        finally:
            if prev is not None:
                os.environ["RUNMYCAMPUS_AI_ENABLED"] = prev

    def test_approval_handoff_requires_human_gate(self):
        rec = structure_ai_recommendation(
            recommendation_key="workflow.rules",
            title="Workflow hygiene",
            explanation="Review schedule gaps.",
            confidence=0.9,
            proposed_action="Open scheduled reports hub.",
        )
        handoff = build_ai_approval_handoff(
            recommendation=rec,
            approved=True,
            approver_user_id=42,
            notes="Validated by operator.",
        )
        self.assertEqual(handoff.get("status"), "approved_for_execution")
        self.assertEqual(handoff.get("approved_by_user_id"), 42)
        self.assertTrue(handoff.get("requires_human_approval"))
