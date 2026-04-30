"""Tests for admin return-to-origin (add_view redirect to next, safe URL)."""

import uuid

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from apps.policies.models import CountryProfile

User = get_user_model()

# auth.User is registered on both admin sites; tests use CountryProfile for add redirect.
_ADD = "admin:policies_countryprofile_add"
_LIST = "admin:policies_countryprofile_changelist"


class AdminAddViewReturnToOriginTests(TestCase):
    """Test that add_view redirects to request.POST['next'] when safe."""

    def setUp(self):
        self.user = User.objects.create_superuser(
            username="admin_return", email="a@test.com", password="password"
        )
        self.client.force_login(self.user)

    def test_add_page_with_next_includes_hidden_input(self):
        """GET add page with ?next= should render hidden input next in submit row."""
        changelist_url = reverse(_LIST)
        url = reverse(_ADD) + "?next=" + changelist_url
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'name="next"', response.content)
        self.assertIn(b"countryprofile_form", response.content)

    def _countryprofile_post_data(self, next_url: str) -> dict:
        code = f"z{uuid.uuid4().hex[:8]}"
        return {
            "country_code": code,
            "name": "Admin Return Test",
            "timezone": "UTC",
            "default_language": "en",
            "grading_scale": "default",
            "extra": "{}",
            "next": next_url,
            "_save": "Save",
        }, code

    def test_post_add_redirects_to_safe_next(self):
        """POST to add with valid data and next= same-origin URL redirects to next."""
        changelist_url = reverse(_LIST)
        add_url = reverse(_ADD)
        data, code = self._countryprofile_post_data(changelist_url)
        response = self.client.post(add_url, data, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], changelist_url)
        CountryProfile.objects.filter(country_code=code).delete()

    def test_post_add_ignores_external_next(self):
        """POST with next= external URL must not redirect to it (security)."""
        add_url = reverse(_ADD)
        data, code = self._countryprofile_post_data("https://evil.example/phish")
        response = self.client.post(add_url, data, follow=False)
        self.assertEqual(response.status_code, 302)
        self.assertNotIn("evil.example", response["Location"])
        CountryProfile.objects.filter(country_code=code).delete()
