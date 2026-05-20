"""Friction analysis aggregation."""

from __future__ import annotations

from django.test import SimpleTestCase

from services.ai_center.friction_analysis import analyze_friction_signals, friction_topics_for_operator


class AICenterFrictionTests(SimpleTestCase):
    def test_analyze_friction_pii_free(self):
        out = analyze_friction_signals(
            [{"route": "/api-center/", "module": "apicenter", "signal": "slow", "count": 2}]
        )
        self.assertTrue(out["pii_free"])
        self.assertEqual(out["topics"][0]["route"], "/api-center/")

    def test_operator_topics_non_empty(self):
        topics = friction_topics_for_operator()
        self.assertTrue(topics)
