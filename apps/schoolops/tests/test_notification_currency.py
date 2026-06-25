"""Local-first fallback currency for notification bodies (no-DB).

Guards the P1 fix: a payment-received body must never read "Amount: 50 ." with a
bare number and no currency when the caller omits one.
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.schoolops.notification_intent import _ctx_currency


class _School:
    def __init__(self, value=None, raises=False):
        self._value = value
        self._raises = raises

    def resolve_currency(self):
        if self._raises:
            raise RuntimeError("boom")
        return self._value


class CtxCurrencyTests(SimpleTestCase):
    def test_school_currency_wins_and_uppercases(self):
        self.assertEqual(_ctx_currency({"school": _School("ngn")}), "NGN")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="GBP")
    def test_empty_context_falls_back_to_platform_default(self):
        self.assertEqual(_ctx_currency({}), "GBP")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="EUR")
    def test_blank_school_currency_falls_back(self):
        self.assertEqual(_ctx_currency({"school": _School("")}), "EUR")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="USD")
    def test_resolution_error_degrades_to_default(self):
        self.assertEqual(_ctx_currency({"school": _School(raises=True)}), "USD")
