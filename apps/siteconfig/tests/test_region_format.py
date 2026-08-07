"""
Tests for region-aware template filters (format_date, format_currency, format_number).
Requires region_settings context processor for production; tests use mock context.
"""

from datetime import date, datetime
from decimal import Decimal
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings

from apps.siteconfig.currency import get_currency_symbol
from apps.siteconfig.templatetags import region_format
from apps.siteconfig.templatetags.region_format import (
    _date_format_to_django,
    _resolve_currency_context,
    _resolve_pinned_tenant_currency,
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
        # Default is ISO 8601 (Y-m-d) — the locale-neutral fallback when no pattern
        # is supplied (see _date_format_to_django rationale), not a CM-specific d/m/Y.
        self.assertEqual(_date_format_to_django(""), "Y-m-d")


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
        # No date_format in context → locale-neutral ISO 8601 default (Y-m-d).
        ctx = {}
        d = date(2025, 3, 15)
        self.assertEqual(format_date(ctx, d), "2025-03-15")

    def test_datetime(self):
        ctx = {"date_format": "DD/MM/YYYY"}
        dt = datetime(2025, 3, 15, 10, 30)
        self.assertEqual(format_date(ctx, dt), "15/03/2025")


# PLATFORM_DEFAULT_CURRENCY is the canonical platform-currency setting the filter
# reads first (DEFAULT_CURRENCY is only a legacy fallback), so override both.
@override_settings(PLATFORM_DEFAULT_CURRENCY="XAF", DEFAULT_CURRENCY="XAF")
class FormatCurrencyFilterTests(TestCase):
    def test_none_returns_empty(self):
        self.assertEqual(format_currency(None), "")

    def test_xaf_style_routes_through_format_money(self):
        # XAF (CFA franc) has NO minor unit and a SUFFIX symbol: "50 000 FCFA",
        # never the old "FCFA50,000.00". The filter delegates to the currency SoT.
        from apps.registries.currency import format_money

        self.assertEqual(format_currency(12500), format_money(12500, "XAF"))
        rendered = format_currency(12500)
        self.assertTrue(rendered.endswith("FCFA"))  # suffix, not prefix
        self.assertNotIn(".", rendered)  # zero decimals, no fractional part

    def test_invalid_value_returns_str(self):
        self.assertEqual(format_currency("n/a"), "n/a")

    def test_decimal_input(self):
        from apps.registries.currency import format_money

        self.assertEqual(
            format_currency(Decimal("5000.00")), format_money(Decimal("5000.00"), "XAF")
        )


class _FakeRegion:
    """Stand-in default_region carrying locale separators."""

    def __init__(self, decimal_separator=".", thousands_separator=","):
        self.decimal_separator = decimal_separator
        self.thousands_separator = thousands_separator


class _FakeSchool:
    """Stand-in School whose currency resolution is fixed, so the pinned-tenant
    currency tests need no DB row."""

    def __init__(self, currency_code, default_region=None):
        self._currency_code = currency_code
        self.default_region = default_region

    def resolve_currency(self):
        return self._currency_code


def _patch_pin_and_school(pinned_id, school):
    """Context-manager bundle patching the request tenant pin + School lookup.

    Both are imported lazily inside ``_resolve_pinned_tenant_currency`` so patching
    them at their definition module takes effect on the next call.
    """
    qs = mock.Mock()
    qs.select_related.return_value = qs
    qs.first.return_value = school
    objects = mock.Mock()
    objects.filter.return_value = qs
    fake_school_model = mock.Mock()
    fake_school_model.objects = objects
    return (
        mock.patch(
            "apps.tenancy.boundary_core_guard.get_pinned_school_id",
            return_value=pinned_id,
        ),
        mock.patch("apps.schools.models.School", fake_school_model),
        objects,
    )


@override_settings(PLATFORM_DEFAULT_CURRENCY="USD", DEFAULT_CURRENCY="USD")
class PinnedTenantCurrencyTests(SimpleTestCase):
    """The ``format_currency`` filter cannot see template context, so it resolves
    the school's currency from the per-request tenant pin — a tenant in XAF/NGN
    must not see the platform-default "$" on its own money documents."""

    def setUp(self):
        # The per-pin memo is a module-level ContextVar; reset between tests.
        region_format._PINNED_CURRENCY.set(None)

    def test_pinned_tenant_currency_used_for_filter(self):
        pin, school, _ = _patch_pin_and_school("school-ng", _FakeSchool("NGN"))
        with pin, school:
            self.assertEqual(
                format_currency(12500.50),
                f"{get_currency_symbol('NGN')}12,500.50",
            )

    def test_no_pin_falls_back_to_platform_default(self):
        pin, school, _ = _patch_pin_and_school(None, None)
        with pin, school:
            self.assertEqual(
                format_currency(1000), f"{get_currency_symbol('USD')}1,000.00"
            )

    def test_missing_school_row_falls_back_to_platform_default(self):
        pin, school, _ = _patch_pin_and_school("ghost-id", None)
        with pin, school:
            self.assertEqual(
                format_currency(1000), f"{get_currency_symbol('USD')}1,000.00"
            )

    def test_cross_tenant_memo_does_not_bleed(self):
        pin_a, school_a, _ = _patch_pin_and_school("school-cm", _FakeSchool("XAF"))
        with pin_a, school_a:
            self.assertEqual(
                _resolve_pinned_tenant_currency()[0], get_currency_symbol("XAF")
            )
        pin_b, school_b, _ = _patch_pin_and_school("school-ng", _FakeSchool("NGN"))
        with pin_b, school_b:
            # Different pinned school_id => memo is bypassed, NGN resolved fresh.
            self.assertEqual(
                _resolve_pinned_tenant_currency()[0], get_currency_symbol("NGN")
            )

    def test_memo_avoids_requerying_same_pinned_school(self):
        pin, school, objects = _patch_pin_and_school("school-cm", _FakeSchool("XAF"))
        with pin, school:
            _resolve_pinned_tenant_currency()
            _resolve_pinned_tenant_currency()
            _resolve_pinned_tenant_currency()
        # School looked up once; subsequent amounts served from the per-pin memo.
        self.assertEqual(objects.filter.call_count, 1)

    def test_pinned_tenant_separators_localized(self):
        # A francophone region (decimal ",", thousands space) formats accordingly.
        region = _FakeRegion(decimal_separator=",", thousands_separator=" ")
        pin, school, _ = _patch_pin_and_school(
            "school-fr", _FakeSchool("XAF", default_region=region)
        )
        with pin, school:
            symbol, dec_sep, thousands_sep, code = _resolve_pinned_tenant_currency()
        self.assertEqual(symbol, get_currency_symbol("XAF"))
        self.assertEqual(code, "XAF")
        self.assertEqual(dec_sep, ",")
        self.assertEqual(thousands_sep, " ")

    def test_pinned_tenant_separators_default_when_region_missing(self):
        pin, school, _ = _patch_pin_and_school(
            "school-x", _FakeSchool("USD", default_region=None)
        )
        with pin, school:
            _, dec_sep, thousands_sep, _code = _resolve_pinned_tenant_currency()
        self.assertEqual((dec_sep, thousands_sep), (".", ","))

    def test_explicit_context_currency_overrides_pin(self):
        # A context-aware caller passing currency_symbol wins over the pin.
        pin, school, _ = _patch_pin_and_school("school-cm", _FakeSchool("XAF"))
        with pin, school:
            symbol, dec_sep, thousands_sep, _code = _resolve_currency_context(
                {
                    "currency_symbol": "€",
                    "decimal_separator": ",",
                    "thousands_separator": ".",
                }
            )
        self.assertEqual((symbol, dec_sep, thousands_sep), ("€", ",", "."))

    def test_scalar_format_number_uses_pinned_francophone_separators(self):
        # {{ x|format_number }} has no context, so it must resolve the pinned
        # tenant's separators — a francophone region renders "12 500,50".
        region = _FakeRegion(decimal_separator=",", thousands_separator="\xa0")
        pin, school, _ = _patch_pin_and_school(
            "school-cm", _FakeSchool("XAF", default_region=region)
        )
        with pin, school:
            self.assertEqual(format_number(12500.5), "12\xa0500,50")

    def test_scalar_format_number_defaults_to_en_style_without_pin(self):
        pin, school, _ = _patch_pin_and_school(None, None)
        with pin, school:
            self.assertEqual(format_number(12500.5), "12,500.50")


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
