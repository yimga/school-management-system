"""Shared-device safety: the offline outbox client must not flush one user's
queued work under another user's session.

Source-level assertions on static/js/offline-queue-client.js (the file is a
browser IIFE with no export, so we lock the guard at the source level — the
same pattern used by test_wizard_index_polish). The guard:
  * stamps each queued row with the creator (currentUserId from SMS_OFFLINE_CONFIG),
  * refuses to flush a row whose owner differs from the current user, in BOTH
    the localStorage and IndexedDB flush paths,
  * best-effort flushes the leaving user's own queue on logout.
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

_REPO_ROOT = Path(__file__).resolve().parents[3]
_JS = _REPO_ROOT / "static" / "js" / "offline-queue-client.js"


class OfflineQueueOwnerGuardTests(SimpleTestCase):
    def setUp(self):
        self.src = _JS.read_text(encoding="utf-8")

    def test_current_user_id_sourced_from_config(self):
        self.assertIn("function currentUserId()", self.src)
        self.assertIn("getConfig().currentUserId", self.src)

    def test_owner_guard_helper_exists(self):
        self.assertIn("function rowBlockedForCurrentUser(", self.src)
        # Held back only when current user is known AND differs from the owner.
        self.assertIn("String(owner) !== cur", self.src)

    def test_rows_are_stamped_with_owner_on_enqueue(self):
        # Both the IndexedDB row object and the localStorage row carry owner.
        self.assertIn("owner: owner", self.src)
        self.assertEqual(self.src.count("var owner = currentUserId();"), 1)

    def test_guard_wired_into_both_flush_paths(self):
        # rowBlockedForCurrentUser must gate both flushRowsFromLS and
        # flushRowsFromIdb — at least two call sites.
        self.assertGreaterEqual(self.src.count("rowBlockedForCurrentUser(entry)"), 2)

    def test_logout_flush_is_wired(self):
        self.assertIn("function wireLogoutFlush()", self.src)
        self.assertIn("wireLogoutFlush();", self.src)
        self.assertIn("/logout", self.src)
