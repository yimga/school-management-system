import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from apps.schools.models import School


class LeadCaptureAPITests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Lead School",
            slug="lead-school",
            subdomain="lead-school",
            is_active=True,
        )
        self.url = reverse("api:lead-capture")

    def _post(self, payload, ip="127.0.0.1"):
        return self.client.post(
            self.url,
            data=json.dumps(payload),
            content_type="application/json",
            REMOTE_ADDR=ip,
        )

    def test_create_applicant_success(self):
        response = self._post(
            {
                "school_slug": self.school.slug,
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "jane@example.com",
            }
        )
        self.assertEqual(response.status_code, 201)
        data = response.json()
        self.assertTrue(data.get("ok"))
        self.assertIn("applicant_id", data)

    def test_duplicate_returns_existing(self):
        payload = {
            "school_slug": self.school.slug,
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
        }
        first = self._post(payload)
        second = self._post(payload)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 200)
        self.assertIn("already exists", second.json().get("message", ""))

    def test_invalid_email_rejected(self):
        response = self._post(
            {
                "school_slug": self.school.slug,
                "first_name": "Jane",
                "last_name": "Doe",
                "email": "bad-email",
            }
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get("error"), "Invalid email")

    def test_invalid_json_rejected(self):
        response = self.client.post(
            self.url,
            data="{not-valid-json",
            content_type="application/json",
            REMOTE_ADDR="127.0.0.1",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json().get("error"), "Invalid JSON")

    def test_rate_limit_returns_429(self):
        payload = {
            "school_slug": self.school.slug,
            "first_name": "Jane",
            "last_name": "Doe",
            "email": "jane@example.com",
        }
        with patch("apps.api.lead_capture_api.LEAD_CAPTURE_IP_MAX", 1):
            first = self._post(payload, ip="10.10.10.10")
            second = self._post(
                {
                    "school_slug": self.school.slug,
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "email": "jane2@example.com",
                },
                ip="10.10.10.10",
            )
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 429)
        self.assertIn("retry_after", second.json())

    def test_cache_failure_does_not_block_submission(self):
        with patch("apps.api.lead_capture_api.cache.add", side_effect=OSError("cache down")):
            response = self._post(
                {
                    "school_slug": self.school.slug,
                    "first_name": "Jane",
                    "last_name": "Doe",
                    "email": "cache-failure@example.com",
                }
            )
        self.assertEqual(response.status_code, 201)
