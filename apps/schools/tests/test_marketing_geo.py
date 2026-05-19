from django.test import SimpleTestCase

from apps.schools.marketing_geo import marketing_geo_tagline


class MarketingGeoTaglineTests(SimpleTestCase):
    def test_us_tagline(self):
        self.assertIn("U.S.", marketing_geo_tagline("US"))

    def test_fallback_with_country_name(self):
        line = marketing_geo_tagline("XX", "Exampleland")
        self.assertIn("Exampleland", line)
