"""Tests for LIVE activity ticker real-data resolvers."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.siteconfig.cockpit_context import (
    _pick_operator_incident_banner,
    _pick_tenant_incident_banner,
)
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


class OperatorIncidentBannerTests(SimpleTestCase):
    def test_picks_first_warn_or_danger_card(self):
        cockpit = {
            "activity_ticker": {
                "enabled": True,
                "cards": [
                    {"text": "ok", "severity": "success"},
                    {"text": "watch", "severity": "warn"},
                    {"text": "later", "severity": "danger"},
                ],
            }
        }
        picked = _pick_operator_incident_banner(cockpit)
        self.assertEqual(picked["text"], "watch")

    def test_returns_none_when_disabled(self):
        cockpit = {"activity_ticker": {"enabled": False, "cards": [{"severity": "danger"}]}}
        self.assertIsNone(_pick_operator_incident_banner(cockpit))


class TenantIncidentBannerTests(SimpleTestCase):
    def test_picks_from_tenant_activity_ticker_only(self):
        cockpit = {
            "activity_ticker": {
                "enabled": True,
                "cards": [{"text": "operator leak", "severity": "danger"}],
            },
            "tenant_activity_ticker": {
                "enabled": True,
                "cards": [
                    {"text": "ok", "severity": "success"},
                    {"text": "maintenance window", "severity": "warn"},
                ],
            },
        }
        picked = _pick_tenant_incident_banner(cockpit)
        self.assertEqual(picked["text"], "maintenance window")

    def test_returns_none_when_tenant_ticker_disabled(self):
        cockpit = {
            "tenant_activity_ticker": {
                "enabled": False,
                "cards": [{"text": "watch", "severity": "warn"}],
            }
        }
        self.assertIsNone(_pick_tenant_incident_banner(cockpit))


class TenantActivityTickerDefaultsTests(SimpleTestCase):
    def test_factory_enabled_by_default(self):
        from apps.siteconfig.cockpit_tenant_dashboard import _tenant_activity_ticker_defaults

        defaults = _tenant_activity_ticker_defaults()
        self.assertTrue(defaults["enabled"])
        self.assertGreaterEqual(len(defaults["cards"]), 1)

