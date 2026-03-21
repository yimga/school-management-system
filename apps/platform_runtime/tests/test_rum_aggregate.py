"""Unit tests for RUM aggregation (N10 read model)."""

from django.test import TestCase

from apps.platform_runtime.events import emit_platform_event
from apps.platform_runtime.rum_aggregate import summarize_rum_web_vitals


class RumAggregateTests(TestCase):
    def test_summarize_empty(self):
        s = summarize_rum_web_vitals(hours=24, limit_rows=100)
        self.assertEqual(s["beacon_count"], 0)
        self.assertEqual(s["window_hours"], 24)
        self.assertEqual(s["metrics"]["lcp"]["n"], 0)

    def test_summarize_percentiles(self):
        for i in range(5):
            emit_platform_event(
                "rum_web_vitals",
                {
                    "path": "/portal/parent/" if i % 2 == 0 else "/marketing/",
                    "metrics": {"lcp": 1000.0 + i * 100, "cls": 0.01 * i},
                    "navigation_type": "0",
                },
                tenant_id="",
            )
        s = summarize_rum_web_vitals(hours=24, limit_rows=50)
        self.assertEqual(s["beacon_count"], 5)
        self.assertGreaterEqual(s["metrics"]["lcp"]["n"], 1)
        self.assertIsNotNone(s["metrics"]["lcp"]["p50"])
        paths = {p["path"] for p in s["paths_top"]}
        self.assertIn("/portal/parent/", paths)
