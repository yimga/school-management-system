"""Tests for support sanitize + intent router (batches 1332/1333)."""

from django.test import SimpleTestCase

from services.ai.support_intent import SupportIntent, classify_support_intent
from services.ai.support_sanitize import sanitize_support_query


class SupportSanitizeIntentTests(SimpleTestCase):
    def test_sanitize_redacts_email(self):
        out = sanitize_support_query("Contact me at user@school.edu about grades 95")
        self.assertNotIn("user@school.edu", out)
        self.assertIn("[REDACTED", out)

    def test_classify_api_intent(self):
        intent = classify_support_intent("How do I call the REST webhook API?", active_url="/api/v1/")
        self.assertEqual(intent, SupportIntent.API_DEVELOPER_SUPPORT)

    def test_classify_error_intent(self):
        intent = classify_support_intent("I get a 500 error on save", active_url="/grades/")
        self.assertEqual(intent, SupportIntent.TROUBLESHOOTING_ERROR)
