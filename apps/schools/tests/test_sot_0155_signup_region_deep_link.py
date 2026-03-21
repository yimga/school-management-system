"""
§0.1.5 Wave 8 N29: signup deep link ?region=&country_code=&term_preset=&curriculum=
"""

from django.test import TestCase
from django.urls import reverse


class SignupRegionDeepLinkSot0155Tests(TestCase):
    def test_get_signup_passes_region_curriculum_country_term(self):
        url = (
            reverse("signup_school")
            + "?region=EMEA&country_code=GB&term_preset=UK&curriculum=IB%20Diploma"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("EMEA", content)
        self.assertIn("IB Diploma", content)
        self.assertIn('value="GB"', content)
        self.assertIn('option value="UK" selected', content)
