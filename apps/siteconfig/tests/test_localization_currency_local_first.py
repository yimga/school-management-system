"""Wave 3 — localization context emits the TENANT's currency, not just a country map.

The emitted ``localization.currency_code`` now prefers ``School.resolve_currency`` when a
tenant is resolved (so an explicit override or region/country-derived currency wins),
falling back to the static country map only on public/marketing hosts. ``localization``
also now carries the tenant ``timezone``.
"""

from django.test import RequestFactory, SimpleTestCase, override_settings


class _SchoolNGN:
    timezone = "Africa/Lagos"

    def resolve_currency(self):
        return "NGN"


class _SchoolBoom:
    timezone = ""

    def resolve_currency(self):
        raise RuntimeError("boom")


class ResolveCurrencyForRequestTests(SimpleTestCase):
    def _req(self, school=None):
        req = RequestFactory().get("/")
        if school is not None:
            req.school = school
        return req

    def test_school_currency_wins_over_country_map(self):
        from apps.siteconfig.localization_context_processor import (
            _resolve_currency_for_request,
        )

        # Country says US→USD, but the resolved tenant uses NGN — tenant wins.
        self.assertEqual(
            _resolve_currency_for_request(self._req(_SchoolNGN()), "US"), "NGN"
        )

    def test_no_school_falls_back_to_country_map(self):
        from apps.siteconfig.localization_context_processor import (
            _resolve_currency_for_request,
        )

        self.assertEqual(_resolve_currency_for_request(self._req(), "US"), "USD")
        self.assertEqual(_resolve_currency_for_request(self._req(), "NG"), "NGN")

    def test_resolve_error_degrades_to_country_map(self):
        from apps.siteconfig.localization_context_processor import (
            _resolve_currency_for_request,
        )

        self.assertEqual(
            _resolve_currency_for_request(self._req(_SchoolBoom()), "GB"), "GBP"
        )

    def test_timezone_helper(self):
        from apps.siteconfig.localization_context_processor import (
            _resolve_timezone_for_request,
        )

        self.assertEqual(
            _resolve_timezone_for_request(self._req(_SchoolNGN())), "Africa/Lagos"
        )
        self.assertEqual(_resolve_timezone_for_request(self._req()), "")


class PlatformCurrencySymbolTests(SimpleTestCase):
    """``platform_currency_symbol()`` is the operator/control-plane counterpart to
    the per-tenant currency resolution: pages that report the platform's OWN revenue
    (MRR, North Star, cockpit pulse) must render ``PLATFORM_DEFAULT_CURRENCY`` rather
    than a hardcoded ``$`` — so a platform run in XAF/NGN reports in its own currency."""

    def test_matches_configured_platform_currency(self):
        from apps.siteconfig.currency import (
            get_currency_symbol,
            platform_currency_symbol,
        )

        with override_settings(PLATFORM_DEFAULT_CURRENCY="XAF"):
            self.assertEqual(platform_currency_symbol(), get_currency_symbol("XAF"))
        with override_settings(PLATFORM_DEFAULT_CURRENCY="NGN"):
            self.assertEqual(platform_currency_symbol(), get_currency_symbol("NGN"))

    def test_defaults_to_usd_when_unset_or_blank(self):
        from apps.siteconfig.currency import (
            get_currency_symbol,
            platform_currency_symbol,
        )

        with override_settings(PLATFORM_DEFAULT_CURRENCY=""):
            self.assertEqual(platform_currency_symbol(), get_currency_symbol("USD"))

    def test_normalizes_lowercase_code(self):
        from apps.siteconfig.currency import (
            get_currency_symbol,
            platform_currency_symbol,
        )

        # Settings could carry a lowercase code; the helper upper-cases before lookup.
        with override_settings(PLATFORM_DEFAULT_CURRENCY="ngn"):
            self.assertEqual(platform_currency_symbol(), get_currency_symbol("NGN"))


class LocalizationContextShapeTests(SimpleTestCase):
    def test_emits_currency_and_timezone_keys(self):
        from apps.siteconfig.localization_context_processor import localization_context

        ctx = localization_context(RequestFactory().get("/"))
        loc = ctx["localization"]
        self.assertIn("currency_code", loc)
        self.assertIn("timezone", loc)
        self.assertTrue(loc["currency_code"])  # never blank
