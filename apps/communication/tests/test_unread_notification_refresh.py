"""A second message must not vanish because the first is still unread.

Found by an A-Z audit follow-up (2026-07-16).

``_send_in_app`` used ``get_or_create(recipient=…, title=…, is_read=False,
defaults={message, link, …})``. That reads like safe dedupe and is not: Django
applies ``defaults`` ONLY on create, so a second event matching an unread row
returned "exists" and threw the new payload away.

The titles are constant per SENDER, not per event — ``f"New message from
{sender}"`` / ``f"New message in {thread}"`` (communication/signals) — so "same
title" does NOT mean "same event". A teacher's second message to a parent who
had not opened the first was silently dropped, and ``dispatch_event`` reported
success. ``Category.MESSAGES`` fans to IN_APP + PUSH with **no email leg**, so
that inbox row IS the message.

The model already prescribed the cure: ``NotificationManager.notify_unread``
(update_or_create), whose docstring names this exact hazard. The highest-traffic
writer just wasn't using it.
"""

from __future__ import annotations

from django.test import TestCase, override_settings

from apps.accounts.models import User
from apps.finance.models import Notification
from apps.schools.models import School


@override_settings(MULTI_TENANT_BASE_DOMAIN="runmycampus.com")
class UnreadNotificationRefreshTests(TestCase):
    def setUp(self):
        self.school = School.objects.create(
            name="Inbox Academy",
            slug="inbox-academy",
            subdomain="inbox-academy",
            is_active=True,
        )
        self.parent = User.objects.create_user(
            username="inbox_parent",
            email="parent@inbox.test",
            password="password123",
        )

    def _send(self, message: str, link: str = ""):
        from apps.communication.dispatch import dispatch_event

        return dispatch_event(
            "message.received",
            recipient=self.parent,
            context={
                "title": "New message from Mr Smith",  # constant per sender
                "message": message,
                "link": link,
            },
            school=self.school,
            channels=["in_app"],
        )

    def test_second_unread_message_is_not_dropped(self):
        self._send("Homework is due Friday.", link="/threads/1/")
        result = self._send("Your son was suspended today.", link="/threads/2/")

        self.assertEqual(
            result["results"]["in_app"],
            "refreshed",
            "the second message must refresh the unread row, not report a drop",
        )
        row = Notification.objects.get(
            recipient=self.parent, title="New message from Mr Smith", is_read=False
        )
        self.assertEqual(
            row.message,
            "Your son was suspended today.",
            "the parent must see the LATEST message -- the old code kept message #1 "
            "and silently discarded every message after it",
        )
        self.assertEqual(
            row.link, "/threads/2/", "the link must point at the newest message"
        )

    def test_the_unread_row_stays_single(self):
        """The dedupe intent is preserved — one unread row per (recipient, title)."""
        self._send("One")
        self._send("Two")
        self._send("Three")
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.parent,
                title="New message from Mr Smith",
                is_read=False,
            ).count(),
            1,
        )

    def test_a_read_message_starts_a_fresh_row(self):
        """Once read, the next message must land as a NEW unread notification."""
        self._send("First")
        Notification.objects.filter(recipient=self.parent).update(is_read=True)

        result = self._send("Second")

        self.assertEqual(result["results"]["in_app"], "created")
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.parent, is_read=False
            ).count(),
            1,
        )
        self.assertEqual(Notification.objects.filter(recipient=self.parent).count(), 2)

    def test_first_message_still_reports_created(self):
        result = self._send("Hello")
        self.assertEqual(result["results"]["in_app"], "created")
        self.assertEqual(
            Notification.objects.filter(recipient=self.parent).count(), 1
        )

    def test_distinct_titles_do_not_collide(self):
        from apps.communication.dispatch import dispatch_event

        self._send("From Smith")
        dispatch_event(
            "message.received",
            recipient=self.parent,
            context={"title": "New message from Ms Jones", "message": "From Jones"},
            school=self.school,
            channels=["in_app"],
        )
        self.assertEqual(
            Notification.objects.filter(
                recipient=self.parent, is_read=False
            ).count(),
            2,
            "different senders must each get their own unread row",
        )
