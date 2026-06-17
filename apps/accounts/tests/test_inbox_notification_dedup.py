"""Inbox display dedupes duplicate notification titles."""

from __future__ import annotations

from types import SimpleNamespace

from django.test import SimpleTestCase

from apps.accounts.security_posture_notifications import dedupe_notifications_for_inbox


class InboxNotificationDedupTests(SimpleTestCase):
    def test_collapses_duplicate_titles_keeps_newest_first(self):
        rows = [
            SimpleNamespace(title="Quarterly security review due", is_read=False, pk=3),
            SimpleNamespace(title="Quarterly security review due", is_read=False, pk=2),
            SimpleNamespace(title="Other alert", is_read=False, pk=1),
        ]
        out = dedupe_notifications_for_inbox(rows)
        self.assertEqual(len(out), 2)
        self.assertEqual(out[0].pk, 3)
        self.assertEqual(out[1].pk, 1)

    def test_read_and_unread_same_title_both_kept(self):
        rows = [
            SimpleNamespace(title="Same title", is_read=False, pk=2),
            SimpleNamespace(title="Same title", is_read=True, pk=1),
        ]
        out = dedupe_notifications_for_inbox(rows)
        self.assertEqual(len(out), 2)
