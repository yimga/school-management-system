"""Wave 3 — localization context emits the TENANT's currency, not just a country map.

The emitted ``localization.currency_code`` now prefers ``School.resolve_currency`` when a
tenant is resolved (so an explicit override or region/country-derived currency wins),
falling back to the static country map only on public/marketing hosts. ``localization``
also now carries the tenant ``timezone``.
"""

from django.test import RequestFactory, SimpleTestCase


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


class LocalizationContextShapeTests(SimpleTestCase):
    def test_emits_currency_and_timezone_keys(self):
        from apps.siteconfig.localization_context_processor import localization_context

        ctx = localization_context(RequestFactory().get("/"))
        loc = ctx["localization"]
        self.assertIn("currency_code", loc)
        self.assertIn("timezone", loc)
        self.assertTrue(loc["currency_code"])  # never blank
