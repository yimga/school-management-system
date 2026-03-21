"""BR-12: super_views_geo_api module is the implementation; super_views re-exports for URL wiring."""

from django.test import SimpleTestCase


class SuperViewsGeoApiReexportTests(SimpleTestCase):
    def test_super_views_aliases_match_geo_api_module(self):
        from apps.schools import super_views
        from apps.schools import super_views_geo_api as geo

        pairs = [
            ("api_geo_cities", geo.api_geo_cities),
            ("api_geo_timezones", geo.api_geo_timezones),
            ("api_provinces", geo.api_provinces),
            ("api_education_profiles", geo.api_education_profiles),
            ("api_system_blueprint", geo.api_system_blueprint),
            ("api_plans_configurator", geo.api_plans_configurator),
        ]
        for name, fn in pairs:
            with self.subTest(name=name):
                self.assertIs(getattr(super_views, name), fn)
