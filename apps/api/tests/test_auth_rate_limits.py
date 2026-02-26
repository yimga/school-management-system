from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse


class AuthRateLimitTests(TestCase):
    def test_token_obtain_returns_429_when_rate_limited(self):
        with patch("apps.api.auth_views.throttle_ip_request", return_value=(False, 60)):
            response = self.client.post(
                reverse("api:token_obtain_pair"),
                data={"username": "any", "password": "any"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 429)
        payload = response.json()
        self.assertIn("retry_after", payload)

    def test_token_refresh_returns_429_when_rate_limited(self):
        with patch("apps.api.auth_views.throttle_ip_request", return_value=(False, 60)):
            response = self.client.post(
                reverse("api:token_refresh"),
                data={"refresh": "dummy"},
                content_type="application/json",
            )
        self.assertEqual(response.status_code, 429)
        payload = response.json()
        self.assertIn("retry_after", payload)
