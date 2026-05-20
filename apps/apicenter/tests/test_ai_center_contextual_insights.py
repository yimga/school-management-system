"""Contextual micro-insights marker contract."""

from __future__ import annotations

import uuid

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase

from services.ai_center.contextual_insights import get_contextual_tip

User = get_user_model()


class AICenterContextualInsightTests(SimpleTestCase):
    def test_tip_includes_ui_marker(self):
        user = User(username=f"t_{uuid.uuid4().hex[:6]}")
        tip = get_contextual_tip(
            user,
            None,
            "/api-center/",
            "apicenter",
            {"error_code": "timeout"},
        )
        self.assertEqual(tip["ui_marker"], "data-ai-contextual-insight")
        self.assertTrue(tip["tip"])
