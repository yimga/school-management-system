from django.test import TestCase

from apps.siteconfig.global_catalog import GlobalGeoCatalog


class GlobalGeoCatalogTests(TestCase):
    def test_country_normalization_alpha2_to_alpha3(self):
        self.assertEqual(GlobalGeoCatalog.normalize_country_code("ug"), "UGA")
        self.assertEqual(GlobalGeoCatalog.normalize_country_code("USA"), "USA")

    def test_country_list_contains_uganda(self):
        countries = GlobalGeoCatalog.list_countries()
        codes = {item.get("code") for item in countries}
        self.assertIn("UGA", codes)

    def test_city_search_returns_timezone_coordinates(self):
        rows = GlobalGeoCatalog.search_cities(country_code="UGA", query="kampala", limit=5)
        self.assertTrue(rows)
        first = rows[0]
        self.assertEqual(first.get("country_code"), "UGA")
        self.assertIn("timezone", first)
        self.assertIn("latitude", first)
        self.assertIn("longitude", first)

    def test_country_timezones_are_scoped(self):
        ug_tz = GlobalGeoCatalog.list_timezones(country_code="UGA", limit=30)
        self.assertIn("Africa/Kampala", ug_tz)
