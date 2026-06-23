"""Currency local-first helpers for GEOS lane-2 core loop."""

from __future__ import annotations

from django.test import SimpleTestCase, override_settings

from apps.platform_runtime.geos_lane2_core_loop import (
    _platform_default_currency,
    _resolve_tenant_currency,
)


class _SchoolStub:
    def __init__(self, *, currency="", resolve=None, resolve_raises=False):
        self.currency = currency
        self._resolve = resolve
        self._resolve_raises = resolve_raises

    def resolve_currency(self):
        if self._resolve_raises:
            raise RuntimeError("boom")
        if self._resolve is not None:
            return self._resolve
        return ""


class GeosLane2CurrencyTests(SimpleTestCase):
    def test_resolve_tenant_currency_prefers_resolver(self):
        school = _SchoolStub(resolve="NGN", currency="USD")
        self.assertEqual(_resolve_tenant_currency(school), "NGN")

    def test_resolve_tenant_currency_falls_back_to_explicit_field(self):
        school = _SchoolStub(currency="GBP")
        self.assertEqual(_resolve_tenant_currency(school), "GBP")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="EUR")
    def test_resolve_tenant_currency_uses_platform_default(self):
        school = _SchoolStub()
        self.assertEqual(_resolve_tenant_currency(school), "EUR")

    @override_settings(PLATFORM_DEFAULT_CURRENCY="USD")
    def test_platform_default_currency_helper(self):
        self.assertEqual(_platform_default_currency(), "USD")
