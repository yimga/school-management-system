from django.test import TestCase

from apps.siteconfig.global_catalog import GlobalGeoCatalog
from apps.siteconfig.models import WeatherLocation


class GlobalWeatherCatalogSeedTests(TestCase):
    def test_sync_persists_worldwide_catalog_when_live_deps_present(self):
        if not GlobalGeoCatalog.has_live_catalog():
            self.skipTest("pycountry + geonamescache required")

        GlobalGeoCatalog.clear_caches()
        stats = WeatherLocation.sync_from_global_catalog()
        self.assertFalse(stats.get("skipped"))
        self.assertGreater(stats.get("cities_created", 0), 1000)

        GlobalGeoCatalog.clear_caches()
        self.assertTrue(GlobalGeoCatalog.has_persisted_catalog())

        countries = GlobalGeoCatalog.list_countries()
        self.assertGreaterEqual(len(countries), 200)

        paris = GlobalGeoCatalog.search_cities(
            country_code="FRA", query="Paris", limit=10
        )
        self.assertTrue(paris)
        self.assertEqual(paris[0].get("country_code"), "FRA")

    def test_persisted_catalog_survives_without_geonamescache_module(self):
        if not GlobalGeoCatalog.has_live_catalog():
            self.skipTest("pycountry + geonamescache required to seed")

        WeatherLocation.sync_from_global_catalog()
        GlobalGeoCatalog.clear_caches()

        import apps.siteconfig.global_catalog as catalog_module

        original = catalog_module.geonamescache
        catalog_module.geonamescache = None
        try:
            GlobalGeoCatalog.clear_caches()
            self.assertTrue(GlobalGeoCatalog.is_available())
            rows = GlobalGeoCatalog.search_cities(
                country_code="CMR", query="douala", limit=5
            )
            self.assertTrue(rows)
        finally:
            catalog_module.geonamescache = original
            GlobalGeoCatalog.clear_caches()
