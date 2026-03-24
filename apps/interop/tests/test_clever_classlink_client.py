"""Clever/ClassLink native clients: structured responses without credentials (no network)."""

from django.test import SimpleTestCase

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
