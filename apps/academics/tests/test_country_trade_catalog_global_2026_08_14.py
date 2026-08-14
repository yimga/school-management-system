"""Increment (m) — national/regional TVET trade catalogs beyond Cameroon.

Increment (e) shipped only Cameroon + a generic fallback. This adds real national
sets (Nigeria NBTE, Ghana CTVET, Kenya TVETA, South Africa NC(V), India ITI) and a
shared francophone West/Central Africa set, so a vocational school in those
countries lands on a locally-recognizable trade list rather than the generic one.
These tests pin the national sets, the francophone sharing, and that a vocational
school in an un-curated country still gets the generic set (never empty).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.academics.country_trade_catalogs import _TVET_FR, resolve_trade_catalog
from apps.schools.models import School


def _all_trades(catalog):
    return [t for _, trades in catalog for t in trades]


class NationalTradeCatalogTests(SimpleTestCase):
    def test_nigeria_has_nbte_style_trades(self):
        trades = _all_trades(resolve_trade_catalog(School(country_code="NG")))
        self.assertIn("Motor Vehicle Mechanics", trades)
        self.assertIn("Welding & Fabrication", trades)

    def test_kenya_has_tveta_occupations(self):
        trades = _all_trades(resolve_trade_catalog(School(country_code="KE")))
        self.assertIn("Automotive Engineering", trades)
        self.assertIn("Hairdressing & Beauty Therapy", trades)

    def test_south_africa_has_ncv_programmes(self):
        trades = _all_trades(resolve_trade_catalog(School(country_code="ZA")))
        self.assertIn("Fitting & Turning", trades)
        self.assertIn("Boilermaking", trades)

    def test_india_has_iti_trades(self):
        trades = _all_trades(resolve_trade_catalog(School(country_code="IN")))
        self.assertIn("Fitter", trades)
        self.assertIn("Computer Operator & Programming Assistant (COPA)", trades)

    def test_ghana_has_ctvet_trades(self):
        trades = _all_trades(resolve_trade_catalog(School(country_code="GH")))
        self.assertIn("Cosmetology & Beauty Therapy", trades)


class FrancophoneSharedSetTests(SimpleTestCase):
    def test_francophone_countries_share_the_minefop_set(self):
        for iso in ("CI", "SN", "ML", "BF", "TG", "GA", "CD", "MG"):
            catalog = resolve_trade_catalog(School(country_code=iso))
            self.assertEqual(catalog, _TVET_FR, iso)
            trades = _all_trades(catalog)
            self.assertIn("Soudure & Construction Métallique", trades)


class GenericFallbackStillHoldsTests(SimpleTestCase):
    def test_uncurated_country_gets_generic_never_empty(self):
        for iso in ("DE", "JP", "BR", "SA", "XX"):
            catalog = resolve_trade_catalog(School(country_code=iso))
            self.assertTrue(catalog, iso)
            self.assertTrue(any("Welding" in t for t in _all_trades(catalog)), iso)

    def test_cameroon_still_curated(self):
        trades = _all_trades(resolve_trade_catalog(School(country_code="CM")))
        self.assertIn("Welding & Metal Fabrication", trades)
