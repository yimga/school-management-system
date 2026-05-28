"""v4.00.13 — unit tests for apps/api/enrollment_forecast.py.

Covers:
* No school → empty list
* No history → flat projection with band=0
* Real growth → projection ascends with the rate
* Growth rate cap (50% per term)
* Confidence band (1-sigma)
* Horizon respect
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.api.enrollment_forecast import (
    _yoy_growth_rates,
    _stdev,
    build_forecast,
)


class GrowthRateTests(SimpleTestCase):
    def test_yoy_growth_rates_empty(self):
        self.assertEqual(_yoy_growth_rates([]), [])

    def test_yoy_growth_rates_single(self):
        self.assertEqual(_yoy_growth_rates([100]), [])

    def test_yoy_growth_rates_basic(self):
        rates = _yoy_growth_rates([100, 110, 121])
        self.assertEqual(len(rates), 2)
        self.assertAlmostEqual(rates[0], 0.10, places=6)
        self.assertAlmostEqual(rates[1], 0.10, places=6)

    def test_yoy_growth_rates_zero_division_skipped(self):
        rates = _yoy_growth_rates([0, 100, 110])
        self.assertEqual(len(rates), 1, "zero base should be skipped")
        self.assertAlmostEqual(rates[0], 0.10, places=6)


class StdevTests(SimpleTestCase):
    def test_stdev_empty(self):
        self.assertEqual(_stdev([]), 0.0)

    def test_stdev_single(self):
        self.assertEqual(_stdev([0.1]), 0.0)

    def test_stdev_two(self):
        # known: stdev([0.1, 0.2]) with sample formula = ~0.0707
        result = _stdev([0.1, 0.2])
        self.assertGreater(result, 0.05)
        self.assertLess(result, 0.10)


class BuildForecastTests(SimpleTestCase):
    def test_no_school_returns_empty(self):
        self.assertEqual(build_forecast(school=None, current_count=100, horizon_terms=3), [])

    def test_school_without_pk_returns_empty(self):
        class Dummy:
            pk = None
        self.assertEqual(build_forecast(school=Dummy(), current_count=100, horizon_terms=3), [])

    def test_flat_projection_when_no_history(self):
        class Dummy:
            pk = 1
        with patch("apps.api.enrollment_forecast._historical_yearly_counts", return_value=[]):
            forecasts = build_forecast(school=Dummy(), current_count=200, horizon_terms=3)
        self.assertEqual(len(forecasts), 3)
        for f in forecasts:
            self.assertEqual(f["projected"], 200, "flat projection with no history")
            self.assertEqual(f["growth_rate_used"], 0.0)
            self.assertEqual(f["basis_years"], 0)
            self.assertEqual(f["lower_bound"], f["projected"])
            self.assertEqual(f["upper_bound"], f["projected"])

    def test_growth_projection_with_history(self):
        class Dummy:
            pk = 1
        history = [("2023", 100), ("2024", 110), ("2025", 121)]
        with patch("apps.api.enrollment_forecast._historical_yearly_counts", return_value=history):
            forecasts = build_forecast(school=Dummy(), current_count=121, horizon_terms=2)
        self.assertEqual(len(forecasts), 2)
        # First projection should be roughly 121 * 1.10 = 133
        self.assertGreaterEqual(forecasts[0]["projected"], 130)
        self.assertLessEqual(forecasts[0]["projected"], 136)
        # Second projection should compound
        self.assertGreater(forecasts[1]["projected"], forecasts[0]["projected"])
        self.assertEqual(forecasts[0]["basis_years"], 3)

    def test_horizon_clamped_to_5(self):
        class Dummy:
            pk = 1
        with patch("apps.api.enrollment_forecast._historical_yearly_counts", return_value=[]):
            forecasts = build_forecast(school=Dummy(), current_count=100, horizon_terms=99)
        self.assertEqual(len(forecasts), 5, "horizon must cap at 5 terms")

    def test_growth_rate_capped_at_50pct(self):
        """A wild 500% growth should be capped to 50% per term."""
        class Dummy:
            pk = 1
        history = [("Y1", 10), ("Y2", 60)]  # 500% growth
        with patch("apps.api.enrollment_forecast._historical_yearly_counts", return_value=history):
            forecasts = build_forecast(school=Dummy(), current_count=100, horizon_terms=1)
        # 100 * 1.5 = 150 (capped to +50%, not +500%)
        self.assertLessEqual(forecasts[0]["projected"], 150)
        self.assertGreaterEqual(forecasts[0]["projected"], 145)
