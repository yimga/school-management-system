"""
Tests for the real forecast-lane resolver — cockpit_panels_realdata_service.

The forecast lane (templates/partials/cockpit/_forecast_lane.html) renders
MRR / new-schools / incidents 7-day projections from the PlatformPulseSnapshot
daily series. These tests assert:

  * insufficient history (< _FC_MIN_POINTS) hides the lane (resolver -> None),
  * a real series yields exactly 3 well-formed cards,
  * the SVG geometry is continuous + grammar-safe for the `d` attribute,
  * the headline value/prediction track the underlying trend.
"""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.siteconfig import cockpit_panels_realdata_service as svc
from apps.siteconfig.models_pulse_snapshot import PlatformPulseSnapshot

# Characters the partial's band_path / polyline grammar is allowed to contain.
# (digits, decimal point, comma, space, and the SVG commands we emit).
_ALLOWED_PATH_CHARS = set("0123456789., MLZ-")


def _seed(metric_key: str, values: list[int]) -> None:
    """Write one snapshot row per day, oldest-first ending today (UTC)."""
    today = timezone.now().date()
    n = len(values)
    for i, v in enumerate(values):
        PlatformPulseSnapshot.objects.create(
            snapshot_date=today - timedelta(days=(n - 1 - i)),
            metric_key=metric_key,
            raw_value=v,
            display_value=str(v),
        )


class ForecastLaneResolverTests(TestCase):
    def test_insufficient_history_hides_lane(self):
        """Fewer than _FC_MIN_POINTS snapshots -> resolver returns None."""
        _seed(PlatformPulseSnapshot.MRR, [40000, 41000])      # only 2 points
        _seed(PlatformPulseSnapshot.SCHOOLS, [20, 21])
        _seed(PlatformPulseSnapshot.INCIDENTS, [1, 2])
        self.assertIsNone(svc._resolve_forecast_lane())

    def test_partial_metric_missing_hides_lane(self):
        """If even one metric lacks enough history, the whole lane stays hidden."""
        _seed(PlatformPulseSnapshot.MRR, [40000, 41000, 42000, 43000])
        _seed(PlatformPulseSnapshot.SCHOOLS, [20, 21, 22, 23])
        _seed(PlatformPulseSnapshot.INCIDENTS, [1])           # too few
        self.assertIsNone(svc._resolve_forecast_lane())

    def test_real_series_returns_three_cards(self):
        _seed(PlatformPulseSnapshot.MRR, [40000, 41000, 42000, 43000, 44000, 45000, 46000])
        _seed(PlatformPulseSnapshot.SCHOOLS, [20, 21, 21, 22, 23, 24, 26])
        _seed(PlatformPulseSnapshot.INCIDENTS, [3, 2, 2, 1, 2, 2, 2])

        result = svc._resolve_forecast_lane()
        self.assertIsNotNone(result)
        self.assertTrue(result["enabled"])
        cards = result["cards"]
        self.assertEqual(len(cards), 3)
        self.assertEqual([c["slug"] for c in cards], ["mrr", "new_schools", "incidents"])

        for card in cards:
            for key in (
                "label", "value", "prediction", "stroke_color", "fill_color",
                "past_points", "future_points", "band_path", "today_x",
                "caption_left", "caption_right",
            ):
                self.assertIn(key, card, f"{card['slug']} missing {key}")
            # today_x sits on the viewBox midline.
            self.assertEqual(card["today_x"], svc._FC_TODAY_X)
            # Past trace ends where the future trace begins (visual continuity).
            self.assertEqual(card["future_points"][0], card["past_points"][-1])
            # Every plotted y stays inside the 0..56 viewBox band.
            for _x, y in card["past_points"] + card["future_points"]:
                self.assertGreaterEqual(y, 0)
                self.assertLessEqual(y, 56)
            # band_path is grammar-safe for direct injection into the SVG `d` attr.
            self.assertTrue(card["band_path"].startswith("M"))
            self.assertTrue(card["band_path"].rstrip().endswith("Z"))
            self.assertTrue(
                set(card["band_path"]) <= _ALLOWED_PATH_CHARS,
                f"{card['slug']} band_path has unexpected chars: "
                f"{set(card['band_path']) - _ALLOWED_PATH_CHARS}",
            )

    def test_rising_mrr_reflected_in_value_and_prediction(self):
        _seed(PlatformPulseSnapshot.MRR, [40000, 41000, 42000, 43000, 44000, 45000, 46000])
        _seed(PlatformPulseSnapshot.SCHOOLS, [20, 21, 22, 23, 24, 25, 26])
        _seed(PlatformPulseSnapshot.INCIDENTS, [2, 2, 2, 2, 2, 2, 2])

        cards = {c["slug"]: c for c in svc._resolve_forecast_lane()["cards"]}
        mrr = cards["mrr"]
        # Projection extends above today's $46k, formatted with the k-suffix.
        self.assertTrue(mrr["value"].startswith("$"))
        self.assertIn("k", mrr["value"])
        self.assertIn("rising", str(mrr["prediction"]))
        # Flat incidents read as steady-low, not a fabricated spike.
        self.assertEqual(cards["incidents"]["value"], "2")
        self.assertIn("low", str(cards["incidents"]["prediction"]))

    def test_flat_series_is_handled_without_zero_division(self):
        """A perfectly flat series must not crash the y-mapping (span == 0)."""
        _seed(PlatformPulseSnapshot.MRR, [42000, 42000, 42000, 42000])
        _seed(PlatformPulseSnapshot.SCHOOLS, [22, 22, 22, 22])
        _seed(PlatformPulseSnapshot.INCIDENTS, [0, 0, 0, 0])

        result = svc._resolve_forecast_lane()
        self.assertIsNotNone(result)
        self.assertEqual(len(result["cards"]), 3)
        # Flat incidents at zero -> "0" with a "none expected" caption.
        incidents = next(c for c in result["cards"] if c["slug"] == "incidents")
        self.assertEqual(incidents["value"], "0")
