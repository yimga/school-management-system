"""
Tests for cockpit_platform_pulse_service — v3.58.0 (2026-05-22).

Asserts the empty-state contract: even when every model query fails, the
service still returns exactly 6 cards in slot-order with value="—" and
severity="muted" so the cockpit layout holds.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase

from apps.siteconfig import cockpit_platform_pulse_service as svc


class PulseServiceEmptyStateContract(SimpleTestCase):
    def setUp(self):
        # Each test gets a clean cache so the 60s TTL doesn't leak between cases.
        try:
            svc.invalidate_pulse_cards_cache()
        except Exception:
            pass
        self._spark_patch = mock.patch.object(svc, "_sparkline_csv_for_metric", return_value="")
        self._spark_patch.start()

    def tearDown(self):
        self._spark_patch.stop()

    def test_all_resolvers_failing_returns_6_empty_cards(self):
        """When every resolver crashes, 6 ``—`` cards still render."""
        with mock.patch.object(svc, "_resolve_schools_card", side_effect=Exception("boom")), \
             mock.patch.object(svc, "_resolve_incidents_card", side_effect=Exception("boom")), \
             mock.patch.object(svc, "_resolve_countries_card", side_effect=Exception("boom")), \
             mock.patch.object(svc, "_resolve_mrr_card", side_effect=Exception("boom")), \
             mock.patch.object(svc, "_resolve_webhooks_card", side_effect=Exception("boom")), \
             mock.patch.object(svc, "_resolve_pipeline_card", side_effect=Exception("boom")):
            cards = svc.resolve_pulse_cards()

        self.assertEqual(len(cards), 6)
        for card in cards:
            self.assertEqual(card["value"], "—")
            self.assertEqual(card["severity"], "muted")
            # Empty-state cards never invent a delta — keeps the UI honest.
            self.assertEqual(card["delta"], "")
            self.assertIsNone(card["delta_direction"])

    def test_card_order_is_stable(self):
        """Slots must always come back in Schools/Incidents/Countries/MRR/Webhooks/Pipeline order."""
        with mock.patch.object(svc, "_resolve_schools_card", return_value=None), \
             mock.patch.object(svc, "_resolve_incidents_card", return_value=None), \
             mock.patch.object(svc, "_resolve_countries_card", return_value=None), \
             mock.patch.object(svc, "_resolve_mrr_card", return_value=None), \
             mock.patch.object(svc, "_resolve_webhooks_card", return_value=None), \
             mock.patch.object(svc, "_resolve_pipeline_card", return_value=None):
            cards = svc.resolve_pulse_cards()

        heads = [str(c["head"]) for c in cards]
        # _() returns lazy strings; comparison via str() resolves them.
        self.assertEqual(heads, ["Schools", "Incidents", "Countries", "MRR", "Webhooks", "Pipeline"])

    def test_partial_failure_keeps_other_cards_real(self):
        """If 1 resolver returns real data and 5 fail, only that 1 carries a real value."""
        real_schools = {
            "head": "Schools", "severity": "ok", "value": "42",
            "label": "Healthy", "delta": "", "delta_direction": None,
        }
        with mock.patch.object(svc, "_resolve_schools_card", return_value=real_schools), \
             mock.patch.object(svc, "_resolve_incidents_card", return_value=None), \
             mock.patch.object(svc, "_resolve_countries_card", side_effect=Exception("boom")), \
             mock.patch.object(svc, "_resolve_mrr_card", side_effect=Exception("boom")), \
             mock.patch.object(svc, "_resolve_webhooks_card", side_effect=Exception("boom")), \
             mock.patch.object(svc, "_resolve_pipeline_card", side_effect=Exception("boom")):
            cards = svc.resolve_pulse_cards()

        self.assertEqual(cards[0]["value"], "42")
        for card in cards[1:]:
            self.assertEqual(card["value"], "—")

    def test_attach_sparkline_sets_csv_when_history_exists(self):
        card = {"head": "Schools", "value": "42"}
        with mock.patch.object(svc, "_sparkline_csv_for_metric", return_value="1,2,3,4"):
            svc._attach_sparkline(card, "schools")
        self.assertEqual(card["spark_points"], "1,2,3,4")
