"""Tests for LIVE activity ticker real-data resolvers."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.siteconfig.cockpit_activity_ticker_realdata import (
    MAX_CARDS_TOTAL,
    merge_activity_ticker_card_lists,
    merge_activity_ticker_sections,
)


class ActivityTickerMergeTests(SimpleTestCase):
    def test_merge_dedupes_and_preserves_order(self):
        base = [{"text": "A", "timestamp": "1m ago"}]
        extra = [
            {"text": "A", "timestamp": "1m ago"},
            {"text": "B", "timestamp": "2m ago"},
        ]
        merged = merge_activity_ticker_card_lists(base, extra, max_total=8)
        self.assertEqual(len(merged), 2)
        self.assertEqual(merged[0]["text"], "A")
        self.assertEqual(merged[1]["text"], "B")

    def test_merge_sections_keeps_demo_cards(self):
        cockpit = {
            "activity_ticker": {
                "enabled": True,
                "cards": [{"text": "Demo event", "timestamp": "now"}],
            }
        }
        overlay = {
            "activity_ticker": {
                "cards": [{"text": "Live event", "timestamp": "1m ago"}],
            }
        }
        merged = merge_activity_ticker_sections(cockpit, overlay)
        cards = merged["activity_ticker"]["cards"]
        self.assertEqual(len(cards), 2)
        self.assertTrue(merged["activity_ticker"]["enabled"])

    def test_max_cards_total_at_least_twelve(self):
        self.assertGreaterEqual(MAX_CARDS_TOTAL, 12)

