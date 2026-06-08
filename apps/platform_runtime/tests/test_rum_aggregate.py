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
        self.assertEqual(s["layout"]["sample_count"], 0)

    def test_summarize_percentiles(self):
        for i in range(5):
            emit_platform_event(
                "rum_web_vitals",
                {
                    "path": "/portal/parent/" if i % 2 == 0 else "/marketing/",
                    "metrics": {"lcp": 1000.0 + i * 100, "cls": 0.01 * i},
                    "layout": {
                        "version": 1,
                        "observed_count": 10,
                        "overflow_count": i % 2,
                        "inline_overflow_count": i % 2,
                        "block_overflow_count": 0,
                        "max_inline_overflow_px": i * 10,
                        "max_block_overflow_px": 0,
                        "viewport_class": "B",
                        "direction": "ltr",
                    },
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
        self.assertEqual(s["layout"]["sample_count"], 5)
        self.assertEqual(s["layout"]["overflow_beacon_count"], 2)
        self.assertEqual(s["layout"]["max_inline_overflow_px"], 40)
        self.assertEqual(s["layout"]["viewport_classes"]["B"], 5)

    def test_malformed_historical_layout_is_ignored(self):
        emit_platform_event(
            "rum_web_vitals",
            {
                "path": "/bad/",
                "metrics": {},
                "layout": {
                    "version": 1,
                    "observed_count": "broken",
                    "overflow_count": {"invalid": True},
                },
            },
            tenant_id="",
        )
        summary = summarize_rum_web_vitals(hours=24, limit_rows=10)
        self.assertEqual(summary["layout"]["sample_count"], 1)
        self.assertEqual(summary["layout"]["overflow_count"], 0)
