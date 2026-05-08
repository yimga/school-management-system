"""Tests for the marketing form honeypot — bots that auto-fill ``website_url``
get silently redirected to the success URL without webhooking the data.
"""

from __future__ import annotations

from django.test import Client, TestCase
from django.urls import reverse


class MarketingFormHoneypotTests(TestCase):
    def setUp(self):
        self.client = Client()

    def _post(self, url_name: str, **fields):
        return self.client.post(reverse(url_name), data=fields, follow=False)

    def test_demo_form_with_honeypot_redirects_silent_success(self):
        resp = self._post(
            "marketing_book_demo_submit",
            website_url="http://spam.example.com/",
            name="Bot",
            email="bot@example.com",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("submitted=1", resp["Location"])

    def test_contact_form_with_honeypot_redirects_silent_success(self):
        resp = self._post(
            "marketing_contact_submit",
            website_url="http://spam.example.com/",
            name="Bot",
            email="bot@example.com",
            inquiry_type="general",
            message="hi",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("submitted=1", resp["Location"])

    def test_security_packet_form_with_honeypot_redirects_silent_success(self):
        resp = self._post(
            "marketing_security_packet_submit",
            website_url="http://spam.example.com/",
            name="Bot",
            email="bot@example.com",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("submitted=1", resp["Location"])

    def test_demo_form_without_honeypot_processes_normally(self):
        resp = self._post(
            "marketing_book_demo_submit",
            name="Real User",
            email="user@example.com",
            school="Test School",
            message="Please demo",
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/demo/", resp["Location"])
        # Without webhook configured, an email present still flips to ?submitted=1.
        self.assertIn("submitted=1", resp["Location"])
