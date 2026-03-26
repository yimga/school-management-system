"""Clever/ClassLink native clients: structured responses without credentials (no network)."""

from django.test import SimpleTestCase
from unittest.mock import patch

from apps.interop.clever_classlink_client import (
    clever_list_schools,
    clever_list_sections,
    clever_list_users,
    clever_oauth_token_exchange,
    classlink_list_courses,
    classlink_roster_ping,
)


class CleverClasslinkClientTests(SimpleTestCase):
    def test_clever_missing_token(self):
        self.assertEqual(clever_list_users("")["error"], "missing_token")
        self.assertEqual(clever_list_schools("")["error"], "missing_token")
        self.assertEqual(clever_list_sections("x")["error"], "missing_token")

    def test_classlink_missing_token(self):
        self.assertEqual(classlink_roster_ping("")["error"], "missing_token")
        self.assertEqual(classlink_list_courses("")["error"], "missing_token")

    def test_oauth_missing_fields(self):
        self.assertEqual(
            clever_oauth_token_exchange("", "", "", "")["error"], "missing_fields"
        )

    @patch("apps.interop.clever_classlink_client.urllib.request.urlopen")
    def test_oauth_exchange_success(self, mock_urlopen):
        mock_resp = mock_urlopen.return_value.__enter__.return_value
        mock_resp.read.return_value = b'{"access_token":"tok","token_type":"bearer"}'
        data = clever_oauth_token_exchange(
            "client_id",
            "client_secret",
            "auth_code",
            "https://example.com/callback",
        )
        self.assertEqual(data.get("access_token"), "tok")
