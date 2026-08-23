"""Currency display formatting — regression seals for the CFA/XAF fix.

Sealed here (2026-08-07): tenant money surfaces (invoices, receipts, statements,
report cards) rendered the CFA franc as ``FCFA50,000.00`` — the wrong symbol
position AND two bogus decimals — because the formatters hardcoded ``f"{x:,.2f}"``
and a prefixed symbol, ignoring that XAF/XOF have zero minor units. Everything now
routes through ``apps.registries.currency.format_money``.
"""

from django.test import SimpleTestCase

from apps.registries.currency import format_money, get_currency_decimal_places

NBSP = " "


class CurrencyDecimalPlacesTests(SimpleTestCase):
    def test_cfa_franc_has_zero_minor_units(self):
        self.assertEqual(get_currency_decimal_places("XAF"), 0)
        self.assertEqual(get_currency_decimal_places("XOF"), 0)
        # Case-insensitive.
        self.assertEqual(get_currency_decimal_places("xaf"), 0)

    def test_common_currencies_two(self):
        for code in ("USD", "NGN", "EUR", "GBP", "KES"):
            self.assertEqual(get_currency_decimal_places(code), 2, code)

    def test_zero_and_three_decimal_exceptions(self):
        self.assertEqual(get_currency_decimal_places("JPY"), 0)
        self.assertEqual(get_currency_decimal_places("KWD"), 3)

    def test_unknown_and_empty_default_to_two(self):
        self.assertEqual(get_currency_decimal_places("ZZZ"), 2)
        self.assertEqual(get_currency_decimal_places(""), 2)


class FormatMoneyTests(SimpleTestCase):
    def test_xaf_is_zero_decimal_space_grouped_fcfa_suffix(self):
        # The headline bug: was "FCFA50,000.00"; must be "50 000 FCFA".
        self.assertEqual(format_money(50000, "XAF"), f"50{NBSP}000{NBSP}FCFA")
        self.assertEqual(
            format_money(1500000, "XAF"), f"1{NBSP}500{NBSP}000{NBSP}FCFA"
        )

    def test_xof_suffix_cfa(self):
        self.assertEqual(format_money(50000, "XOF"), f"50{NBSP}000{NBSP}CFA")

    def test_usd_unchanged_prefix_two_decimals(self):
        self.assertEqual(format_money(50000, "USD"), "$50,000.00")
        self.assertEqual(format_money(1234.5, "USD"), "$1,234.50")

    def test_ngn_unchanged_prefix(self):
        self.assertEqual(format_money(50000, "NGN"), "₦50,000.00")

    def test_jpy_zero_decimal_but_prefix_not_suffix(self):
        out = format_money(50000, "JPY")
        self.assertNotIn(".", out)  # zero minor units -> no fractional part
        self.assertTrue(out.endswith("50,000"))  # prefixed, not a CFA suffix

    def test_none_returns_empty_and_bad_input_passthrough(self):
        self.assertEqual(format_money(None, "XAF"), "")
        self.assertEqual(format_money("not-a-number", "USD"), "not-a-number")

    def test_explicit_separators_respected_for_non_cfa(self):
        # A francophone-configured non-CFA tenant may override grouping.
        self.assertEqual(
            format_money(1234.5, "EUR", decimal_sep=",", thousands_sep=NBSP),
            f"€1{NBSP}234,50",
        )

    def test_decimal_amounts_round_for_display(self):
        from decimal import Decimal

        self.assertEqual(format_money(Decimal("2500.00"), "XAF"), f"2{NBSP}500{NBSP}FCFA")
        self.assertEqual(format_money(Decimal("19.99"), "USD"), "$19.99")
