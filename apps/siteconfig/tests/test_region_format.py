"""
Tests for region-aware template filters (format_date, format_currency, format_number).
Requires region_settings context processor for production; tests use mock context.
"""

from datetime import date, datetime
from decimal import Decimal

from django.test import TestCase

from apps.siteconfig.templatetags.region_format import (
    _date_format_to_django,
    format_date,
    format_currency,
    format_number,
)


class DateFormatToDjangoTests(TestCase):
    def test_dd_mm_yyyy(self):
        self.assertEqual(_date_format_to_django("DD/MM/YYYY"), "d/m/Y")

    def test_mm_dd_yyyy(self):
        self.assertEqual(_date_format_to_django("MM/DD/YYYY"), "m/d/Y")

    def test_yyyy_mm_dd(self):
        self.assertEqual(_date_format_to_django("YYYY-MM-DD"), "Y-m-d")

    def test_empty_returns_default(self):
        self.assertEqual(_date_format_to_django(""), "d/m/Y")


class FormatDateFilterTests(TestCase):
    def test_none_returns_empty(self):
        ctx = {}
        self.assertEqual(format_date(ctx, None), "")

    def test_cmr_style_dd_mm_yyyy(self):
        ctx = {"date_format": "DD/MM/YYYY"}
        d = date(2025, 3, 15)
        self.assertEqual(format_date(ctx, d), "15/03/2025")

    def test_usa_style_mm_dd_yyyy(self):
        ctx = {"date_format": "MM/DD/YYYY"}
        d = date(2025, 3, 15)
        self.assertEqual(format_date(ctx, d), "03/15/2025")

    def test_iso_style(self):
        ctx = {"date_format": "YYYY-MM-DD"}
        d = date(2025, 3, 15)
        self.assertEqual(format_date(ctx, d), "2025-03-15")

    def test_default_when_no_context_key(self):
        ctx = {}
        d = date(2025, 3, 15)
        self.assertEqual(format_date(ctx, d), "15/03/2025")

    def test_datetime(self):
        ctx = {"date_format": "DD/MM/YYYY"}
        dt = datetime(2025, 3, 15, 10, 30)
        self.assertEqual(format_date(ctx, dt), "15/03/2025")


class FormatCurrencyFilterTests(TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(format_currency(None), "")

    def test_xaf_style(self):
        self.assertEqual(format_currency(12500.50), "FCFA12,500.50")

    def test_invalid_value_returns_str(self):
        self.assertEqual(format_currency("n/a"), "n/a")

    def test_decimal_input(self):
        self.assertEqual(format_currency(Decimal("5000.00")), "FCFA5,000.00")


class FormatNumberFilterTests(TestCase):
    def test_none_returns_empty(self):
        ctx = {}
        self.assertEqual(format_number(ctx, None), "")

    def test_default_two_decimals(self):
        ctx = {"decimal_separator": ".", "thousands_separator": ","}
        self.assertEqual(format_number(ctx, 1234.5), "1,234.50")

    def test_custom_decimals(self):
        ctx = {}
        self.assertEqual(format_number(ctx, 99.999, 0), "100")
        self.assertEqual(format_number(ctx, 99.999, 1), "100.0")

    def test_european_separators(self):
        ctx = {"decimal_separator": ",", "thousands_separator": "."}
        self.assertEqual(format_number(ctx, 1234.56), "1.234,56")
