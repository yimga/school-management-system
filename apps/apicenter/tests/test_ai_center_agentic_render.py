"""Render-path smoke for the agentic Phase-1 surface + wizard NL-intake partial.

These exercise the REAL HTTP + template stack (test client renders
``control_plane_base.html`` + the agentic template; ``render_to_string`` renders
the wizard partial) — the "does it actually render" check a live browser would do,
without needing a running server.
"""

from __future__ import annotations

import os
import uuid
from unittest import mock

from django.template.loader import render_to_string
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from apps.accounts.models import User


class _EnvFlag:
    def __init__(self, **flags):
        self._flags = flags
        self._prev: dict[str, str | None] = {}

    def __enter__(self):
        for k, v in self._flags.items():
            self._prev[k] = os.environ.get(k)
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k, prev in self._prev.items():
            if prev is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prev


class AgenticSurfaceRenderTests(TestCase):
    databases = {"default"}

    def setUp(self):
        self.user = User.objects.create_superuser(
            username=f"op_{uuid.uuid4().hex[:8]}",
            email=f"op_{uuid.uuid4().hex[:6]}@example.com",
            password="x" * 12,
        )
        self.client.force_login(self.user)
        self.url = reverse("super:ai_center_agentic")

    def test_get_renders_when_flag_off(self):
        with _EnvFlag(RMC_AI_AGENTIC_ENABLED=None):
            resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Agentic insights")
        self.assertContains(resp, "RMC_AI_AGENTIC_ENABLED")

    def test_get_renders_when_flag_on(self):
        with _EnvFlag(RMC_AI_AGENTIC_ENABLED="1", RUNMYCAMPUS_AI_ENABLED="1"):
            resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Ask for a read-only insight")
        # The 3 read-only actions are advertised.
        self.assertContains(resp, "summarize_attendance_report")

    def test_post_propose_renders_proposal(self):
        with _EnvFlag(RMC_AI_AGENTIC_ENABLED="1", RUNMYCAMPUS_AI_ENABLED="1"):
            with mock.patch("services.ai_helpers.is_ai_available", return_value=False):
                resp = self.client.post(
                    self.url,
                    {"gen": "propose", "prompt": "give me an attendance summary", "class_id": "5A"},
                )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "summarize_attendance_report")

    def test_post_execute_renders_result_and_writes_audit(self):
        from apps.platform_runtime.models_agentic_audit import AIAgenticActionAudit

        with _EnvFlag(RMC_AI_AGENTIC_ENABLED="1", RUNMYCAMPUS_AI_ENABLED="1"):
            resp = self.client.post(
                self.url,
                {"gen": "execute", "action": "draft_parent_announcement", "topic": "sports day"},
            )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Result")
        self.assertTrue(
            AIAgenticActionAudit.objects.filter(action="draft_parent_announcement").exists()
        )

    def test_post_when_flag_off_does_not_execute(self):
        from apps.platform_runtime.models_agentic_audit import AIAgenticActionAudit

        before = AIAgenticActionAudit.objects.count()
        with _EnvFlag(RMC_AI_AGENTIC_ENABLED=None):
            resp = self.client.post(
                self.url,
                {"gen": "execute", "action": "draft_parent_announcement", "topic": "x"},
            )
        self.assertEqual(resp.status_code, 200)
        # Disabled surface writes no audit row.
        self.assertEqual(AIAgenticActionAudit.objects.count(), before)


class _Step:
    input_type = "structured_form"


class WizardNlIntakePartialRenderTests(SimpleTestCase):
    def test_partial_renders_with_prefill(self):
        html = render_to_string(
            "setup_studio/partials/wizard_nl_intake.html",
            {
                "step": _Step(),
                "form_action_url": "/setup/x/step/",
                "nl_intake_text": "open Mon-Fri 8am",
                "nl_prefill": {"open_days": "Mon-Fri"},
                "nl_applied_fields": ["open_days"],
                "nl_confidence": 0.82,
                "nl_unresolved": ["8am"],
            },
        )
        self.assertIn("Describe it in plain language", html)
        self.assertIn("8am", html)  # unresolved phrase surfaced

    def test_partial_empty_for_non_structured_step(self):
        class _Other:
            input_type = "single_choice"

        html = render_to_string(
            "setup_studio/partials/wizard_nl_intake.html",
            {"step": _Other(), "form_action_url": "/x/"},
        )
        self.assertNotIn("Describe it in plain language", html.strip())
