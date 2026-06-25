"""Local-first charge currency for recurring Stripe payments (no-DB).

Guards the P0 fix: a non-USD tenant's recurring subscription charge must be sent
to the gateway in the school's real currency, never a hardcoded "USD".
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.finance.advanced_payments import _resolve_charge_currency


class _School:
    def __init__(self, value=None, raises=False):
        self._value = value
        self._raises = raises

    def resolve_currency(self):
        if self._raises:
            raise RuntimeError("boom")
        return self._value


class ResolveChargeCurrencyTests(SimpleTestCase):
    @override_settings(PLATFORM_DEFAULT_CURRENCY="EUR")
    def test_none_school_uses_platform_default_not_usd(self):
        # Proves the fallback is the configured platform default, not a literal "USD".
        self.assertEqual(_resolve_charge_currency(None), "EUR")

    def test_tenant_currency_wins(self):
        self.assertEqual(_resolve_charge_currency(_School("NGN")), "NGN")

    def test_tenant_currency_is_upper_cased(self):
        self.assertEqual(_resolve_charge_currency(_School("xaf")), "XAF")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="GBP")
    def test_blank_tenant_currency_falls_back_to_default(self):
        self.assertEqual(_resolve_charge_currency(_School("")), "GBP")
        self.assertEqual(_resolve_charge_currency(_School(None)), "GBP")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="USD")
    def test_resolution_error_degrades_to_default(self):
        self.assertEqual(_resolve_charge_currency(_School(raises=True)), "USD")

    @override_settings()
    def test_missing_setting_defaults_to_usd(self):
        from django.test.utils import override_settings as _os

        with _os(PLATFORM_DEFAULT_CURRENCY=None):
            self.assertEqual(_resolve_charge_currency(None), "USD")
