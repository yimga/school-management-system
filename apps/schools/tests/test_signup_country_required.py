"""Public signup requires country_code (P1 locale/currency cascade)."""

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.test_utils.tenant_hosts import HOST_ROUTED_SETTINGS, public_client


# ROOT_URLCONF makes reverse() produce the public-host path; the HOST is what makes
# the REQUEST arrive there. Without public_client() below, UrlConfSwitcherMiddleware
# would serve every post from config.urls -- the developer urlconf.
@override_settings(
    RATELIMIT_ENABLE=False,
    ROOT_URLCONF="config.public_urls",
    **HOST_ROUTED_SETTINGS,
)
class SignupCountryRequiredTests(TestCase):
    def setUp(self):
        super().setUp()
        self.client = public_client()

    def test_post_without_country_surfaces_required_error(self):
        response = self.client.post(
            reverse("signup_school"),
            {
                "name": "Cascade Academy",
                "slug": "cascade-academy",
                "email": "owner@cascade.test",
                "country_code": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Country is required")

    def test_post_with_invalid_country_code_rejected(self):
        response = self.client.post(
            reverse("signup_school"),
            {
                "name": "Cascade Academy",
                "slug": "cascade-academy-2",
                "email": "owner2@cascade.test",
                "country_code": "ZZ",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select a valid country from the list")

    def test_json_post_without_country_returns_400(self):
        response = self.client.post(
            reverse("signup_school"),
            {
                "name": "Cascade Academy",
                "slug": "cascade-academy-3",
                "email": "owner3@cascade.test",
                "country_code": "",
            },
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload.get("ok"))
        errors = payload.get("errors", [])
        self.assertTrue(
            any("Country is required" in str(err) for err in errors),
            errors,
        )
