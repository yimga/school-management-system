"""
§0.1.5 Wave 8 N29: signup deep link ?region=&country_code=&term_preset=&curriculum=
"""

from django.test import TestCase, override_settings
from django.urls import reverse


class SignupRegionDeepLinkSot0155Tests(TestCase):
    def test_get_signup_passes_region_curriculum_country_term(self):
        # term_preset is now a radio-card group (was a <select>) and the UK
        # calendar preset's code is "uk-3-term" (was the bare "UK"). The deep
        # link still pre-selects the matching card.
        url = (
            reverse("signup_school")
            + "?region=EMEA&country_code=GB&term_preset=uk-3-term&curriculum=IB%20Diploma"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("EMEA", content)
        self.assertIn("IB Diploma", content)
        self.assertIn('value="GB"', content)
        self.assertRegex(content, r'name="term_preset" value="uk-3-term"\s*checked')

    def test_get_signup_prefills_demo_query_params(self):
        url = (
            reverse("signup_school")
            + "?ref=demo&school_name=Demo%20Academy&email=lead%40example.edu&slug=demo-academy"
        )
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('value="Demo Academy"', content)
        self.assertIn('value="lead@example.edu"', content)
        self.assertIn('value="demo-academy"', content)
        self.assertIn("You opened signup from the demo", content)

    @override_settings(
        MARKETING_DEMO_TENANT_URL="",
        TENANT_EXAMPLE_SLUG=None,
        MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    )
    def test_demo_signup_shows_return_bar_with_demo_school_fallback(self):
        response = self.client.get(
            reverse("signup_school") + "?ref=demo&school_name=X"
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("data-rmc-signup-demo-return-bar", content)
        self.assertIn("https://demo-school.runmycampus.com", content)

    @override_settings(
        MARKETING_DEMO_TENANT_URL="",
        TENANT_EXAMPLE_SLUG=None,
        MULTI_TENANT_BASE_DOMAIN="runmycampus.com",
    )
    def test_demo_signup_post_validation_keeps_ref_and_return_bar(self):
        url = reverse("signup_school")
        response = self.client.post(
            url,
            {
                "name": "",
                "slug": "",
                "email": "",
                "country_code": "",
                "term_preset": "",
                "signup_ref": "demo",
            },
        )
        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("You opened signup from the demo", content)
        self.assertIn("data-rmc-signup-demo-return-bar", content)
        self.assertIn('name="signup_ref"', content)
