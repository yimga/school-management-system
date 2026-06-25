"""Local-first currency for aid / scholarship money (no-DB).

Guards the P1 fix: scholarship disbursement + net-price estimate must carry the
school's real currency, not a hardcoded "USD".
"""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.finance.aid_services import _resolve_aid_currency


class _School:
    def __init__(self, value=None, raises=False):
        self._value = value
        self._raises = raises

    def resolve_currency(self):
        if self._raises:
            raise RuntimeError("boom")
        return self._value


class ResolveAidCurrencyTests(SimpleTestCase):
    def test_explicit_value_wins_and_uppercases(self):
        self.assertEqual(_resolve_aid_currency("ngn"), "NGN")
        self.assertEqual(_resolve_aid_currency("USD"), "USD")

    def test_school_currency_when_no_explicit(self):
        self.assertEqual(_resolve_aid_currency(None, school=_School("XAF")), "XAF")
        self.assertEqual(_resolve_aid_currency("", school=_School("eur")), "EUR")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="GBP")
    def test_falls_back_to_platform_default(self):
        self.assertEqual(_resolve_aid_currency(None), "GBP")
        self.assertEqual(_resolve_aid_currency(None, school=_School("")), "GBP")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="ZAR")
    def test_school_resolution_error_degrades_to_default(self):
        self.assertEqual(
            _resolve_aid_currency(None, school=_School(raises=True)), "ZAR"
        )

    @override_settings(PLATFORM_DEFAULT_CURRENCY="EUR")
    def test_unknown_school_id_no_db_degrades_to_default(self):
        # No DB in SimpleTestCase -> the School lookup fails and degrades safely.
        self.assertEqual(_resolve_aid_currency(None, school_id=999999), "EUR")
