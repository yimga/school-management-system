"""NotificationManager.notify_unread — the SOT for constant/recurring-title notifications.

Notification carries a partial-unique constraint
``uniq_unread_notification_per_recipient_title`` (at most ONE unread row per
``(recipient, title)``). A plain ``Notification.objects.create(...)`` with a
constant title raised ``IntegrityError`` the SECOND time the same recipient got
the same title while the first row was still unread — a 500, a silently-swallowed
drop, or an aborted notify loop depending on the call site. Every such site now
routes through ``Notification.objects.notify_unread(...)``; this locks the
contract those sites depend on.

The ``test_plain_create_raises_on_second_unread`` sanity test fails loudly if the
constraint ever stops being enforced in the test DB (which would make every other
assertion here meaningless).
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.finance.models import Notification

TITLE = "Payment Recorded"


class NotifyUnreadManagerTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username="notify_unread_user",
            email="notify_unread@example.com",
            password="Test1234!long",
        )
        cls.other = User.objects.create_user(
            username="notify_unread_other",
            email="notify_unread_other@example.com",
            password="Test1234!long",
        )

    def _unread(self, recipient=None, title=TITLE):
        return Notification.objects.filter(
            recipient=recipient or self.user, title=title, is_read=False
        )

    # --- the constraint is real in the test DB (else nothing else here matters) ---
    def test_plain_create_raises_on_second_unread(self):
        Notification.objects.create(
            recipient=self.user, title=TITLE, message="first"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Notification.objects.create(
                    recipient=self.user, title=TITLE, message="second"
                )

    # --- core contract ---
    def test_first_call_creates_one_unread_row(self):
        note = Notification.objects.notify_unread(
            recipient=self.user,
            title=TITLE,
            message="first",
            severity=Notification.Severity.INFO,
        )
        self.assertIsNotNone(note.pk)
        self.assertFalse(note.is_read)
        self.assertEqual(self._unread().count(), 1)

    def test_second_call_refreshes_same_row_no_duplicate(self):
        first = Notification.objects.notify_unread(
            recipient=self.user, title=TITLE, message="first"
        )
        # Would have raised IntegrityError via a plain create():
        second = Notification.objects.notify_unread(
            recipient=self.user, title=TITLE, message="second", link="/x/"
        )
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(self._unread().count(), 1)
        second.refresh_from_db()
        self.assertEqual(second.message, "second")
        self.assertEqual(second.link, "/x/")
        self.assertFalse(second.is_read)

    def test_recipient_id_form_dedups_too(self):
        first = Notification.objects.notify_unread(
            recipient_id=self.user.pk, title=TITLE, message="first"
        )
        second = Notification.objects.notify_unread(
            recipient_id=self.user.pk, title=TITLE, message="second"
        )
        self.assertEqual(second.pk, first.pk)
        self.assertEqual(self._unread().count(), 1)

    def test_distinct_recipients_get_distinct_rows(self):
        Notification.objects.notify_unread(
            recipient=self.user, title=TITLE, message="mine"
        )
        Notification.objects.notify_unread(
            recipient=self.other, title=TITLE, message="theirs"
        )
        self.assertEqual(self._unread(self.user).count(), 1)
        self.assertEqual(self._unread(self.other).count(), 1)

    def test_read_row_does_not_block_a_new_unread(self):
        # A read row with the same (recipient, title) is outside the partial index,
        # so a fresh unread notification must still be created.
        Notification.objects.create(
            recipient=self.user, title=TITLE, message="old", is_read=True
        )
        note = Notification.objects.notify_unread(
            recipient=self.user, title=TITLE, message="new"
        )
        self.assertFalse(note.is_read)
        self.assertEqual(self._unread().count(), 1)
        self.assertEqual(
            Notification.objects.filter(recipient=self.user, title=TITLE).count(), 2
        )

    def test_null_recipient_falls_back_to_plain_create(self):
        # NULL recipients are distinct in the partial-unique index, so dedup does
        # not apply — each call must create its own platform/global row.
        Notification.objects.notify_unread(title="Platform notice", message="a")
        Notification.objects.notify_unread(title="Platform notice", message="b")
        self.assertEqual(
            Notification.objects.filter(
                recipient__isnull=True, title="Platform notice"
            ).count(),
            2,
        )

    def test_returns_instance_drop_in_for_create(self):
        note = Notification.objects.notify_unread(
            recipient=self.user, title=TITLE, message="m"
        )
        self.assertIsInstance(note, Notification)
        self.assertEqual(note.recipient_id, self.user.pk)
