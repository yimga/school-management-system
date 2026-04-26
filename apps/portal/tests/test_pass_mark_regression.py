"""Regression guards for slim/blank ``pass_mark`` in portal performance math (RunMyCampus)."""

from decimal import Decimal
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from apps.portal.services import _empty_performance_data, _pass_mark_as_float


class PassMarkCoercionTests(TestCase):
    """``_pass_mark_as_float`` must never raise; blank/invalid uses default (10.0)."""

    def test_pass_mark_none_empty_and_whitespace_default(self):
        self.assertEqual(_pass_mark_as_float(None), 10.0)
        self.assertEqual(_pass_mark_as_float(""), 10.0)
        self.assertEqual(_pass_mark_as_float("   "), 10.0)

    def test_pass_mark_invalid_string_default(self):
        self.assertEqual(_pass_mark_as_float("not-a-number"), 10.0)
        self.assertEqual(_pass_mark_as_float("12a"), 10.0)

    def test_pass_mark_numeric_like_values(self):
        self.assertEqual(_pass_mark_as_float(12), 12.0)
        self.assertEqual(_pass_mark_as_float(12.5), 12.5)
        self.assertEqual(_pass_mark_as_float(Decimal("9.25")), 9.25)
        self.assertEqual(_pass_mark_as_float("7"), 7.0)
        self.assertEqual(_pass_mark_as_float("7.5"), 7.5)


class EmptyPerformancePassMarkTests(TestCase):
    """Dashboard performance shell must stay render-safe when settings are slim."""

    def setUp(self):
        cache.clear()

    @patch("apps.portal.services.get_effective_site_settings")
    def test_empty_performance_data_with_blank_pass_mark(self, geff):
        geff.return_value = type(
            "SS",
            (),
            {"pass_mark": ""},
        )()
        out = _empty_performance_data(school=None)
        self.assertEqual(out["pass_mark"], 10.0)
        self.assertIn("trend", out)

    @patch("apps.portal.services.get_effective_site_settings")
    def test_empty_performance_data_with_garbage_pass_mark(self, geff):
        geff.return_value = type("SS", (), {"pass_mark": "??"})()
        out = _empty_performance_data(school=None)
        self.assertEqual(out["pass_mark"], 10.0)
