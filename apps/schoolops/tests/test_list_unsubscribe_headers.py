"""Tests for List-Unsubscribe header resolution (2026-06-06).

Gmail/Yahoo 2024 bulk-sender rules treat a missing List-Unsubscribe as a spam
signal — but it must NEVER appear on transactional/security mail (verification,
password reset), which users must not be able to unsubscribe from.
"""

from django.test import SimpleTestCase, override_settings

from apps.schoolops.email_delivery import _resolve_list_unsubscribe_target


class ListUnsubscribeTargetTests(SimpleTestCase):
    def test_transactional_never_unsubscribable(self):
        with override_settings(
            RMC_LIST_UNSUBSCRIBE_URL="https://runmycampus.com/u/x",
            RMC_LIST_UNSUBSCRIBE_MAILTO="unsub@runmycampus.com",
        ):
            self.assertEqual(_resolve_list_unsubscribe_target("transactional"), "")

    def test_bulk_without_config_is_empty(self):
        with override_settings(
            RMC_LIST_UNSUBSCRIBE_URL="", RMC_LIST_UNSUBSCRIBE_MAILTO=""
        ):
            self.assertEqual(_resolve_list_unsubscribe_target("marketing"), "")

    def test_bulk_classes_with_url_and_mailto(self):
        with override_settings(
            RMC_LIST_UNSUBSCRIBE_URL="https://runmycampus.com/u/abc",
            RMC_LIST_UNSUBSCRIBE_MAILTO="unsub@runmycampus.com",
        ):
            for cls in ("marketing", "newsletter", "digest", "announcement"):
                val = _resolve_list_unsubscribe_target(cls)
                self.assertIn("<https://runmycampus.com/u/abc>", val)
                self.assertIn("<mailto:unsub@runmycampus.com>", val)

    def test_mailto_only_wraps_mailto(self):
        with override_settings(
            RMC_LIST_UNSUBSCRIBE_URL="", RMC_LIST_UNSUBSCRIBE_MAILTO="bye@x.com"
        ):
            self.assertEqual(
                _resolve_list_unsubscribe_target("bulk"), "<mailto:bye@x.com>"
            )

    def test_non_https_url_is_rejected(self):
        # Only https endpoints are honored (http is dropped defensively).
        with override_settings(
            RMC_LIST_UNSUBSCRIBE_URL="http://insecure.example/u",
            RMC_LIST_UNSUBSCRIBE_MAILTO="",
        ):
            self.assertEqual(_resolve_list_unsubscribe_target("marketing"), "")

    def test_crlf_in_target_is_dropped(self):
        with override_settings(
            RMC_LIST_UNSUBSCRIBE_URL="https://x.com/u\r\nInjected: 1",
            RMC_LIST_UNSUBSCRIBE_MAILTO="",
        ):
            self.assertEqual(_resolve_list_unsubscribe_target("marketing"), "")
