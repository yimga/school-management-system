"""Help Center view contracts without full HTTP integration DB."""

from django.test import RequestFactory, SimpleTestCase, override_settings
from django.urls import reverse

from config.manager_help_center import _help_center_sections


@override_settings(ROOT_URLCONF="config.manager_urls", ALLOWED_HOSTS=["*"])
class OperatorHelpCenterViewContractTests(SimpleTestCase):
    def test_help_sections_have_three_lanes(self):
        sections = _help_center_sections()
        ids = {s["id"] for s in sections}
        self.assertTrue({"discover", "engage", "operate", "govern"}.issubset(ids))
        for section in sections:
            self.assertTrue(section["cards"])

    def test_manager_help_redirects_to_help_center(self):
        from config.manager_urls import manager_help

        response = manager_help(RequestFactory().get("/help/"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/help-center", response["Location"])

    def test_manager_help_center_reverse(self):
        self.assertIn("/help-center", reverse("manager_help_center"))

    def test_manager_engagement_routes_reverse(self):
        self.assertIn("/feature-center", reverse("manager_feature_center"))
        self.assertIn("/contact-us", reverse("manager_contact_us"))
        self.assertIn("/product-roadmap", reverse("manager_product_roadmap"))
