"""One decision, one notification -- a constant title collapsed them all.

``Notification.objects.notify_unread`` is an UPSERT on
``(recipient, title, is_read=False)`` (finance/models.py::NotificationManager):
at most one unread row per recipient per title, and a second call with the same
title REFRESHES that row instead of adding one.

``apply_request_decision`` passed a title that was constant per status --
"Request Approved" for every approval any requester ever received. So the second
approval overwrote the first row's ``message`` AND its ``link``, and the bell
pointed at whichever request happened to be decided last. ``bulk_decide`` makes
that the normal case rather than the edge case: twenty approvals in one post
produced exactly one notification.

The fix puts the request reference in the title. These tests fail on the
pre-fix tree (one row, wrong link) and pass after it.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import Notification
from apps.requests.models import AccessRequest, RequestDecision
from apps.requests.services import apply_request_decision
from apps.schools.models import School


class OneDecisionOneNotificationTests(TestCase):
    def setUp(self) -> None:
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Notify {uid}", slug=f"notify-{uid}", subdomain=f"notify{uid}",
            is_active=True,
        )
        self.requester = User.objects.create_user(
            username=f"notify_req_{uid}", password="Test1234", role=User.Role.TEACHER
        )
        self.admin = User.objects.create_user(
            username=f"notify_adm_{uid}", password="Test1234", role=User.Role.ADMIN
        )

    def _request(self) -> AccessRequest:
        return AccessRequest.objects.create(
            request_type=AccessRequest.RequestType.DOCUMENT_REQUEST,
            status=AccessRequest.Status.PENDING,
            school=self.school,
            requester=self.requester,
            title="Please",
        )

    def _decide(self, req, decision=RequestDecision.Decision.APPROVED):
        return apply_request_decision(
            request=req, decision=decision, reason="", actor=self.admin
        )

    def test_two_approvals_produce_two_notifications(self) -> None:
        first = self._request()
        second = self._request()
        self._decide(first)
        self._decide(second)

        rows = Notification.objects.filter(recipient=self.requester)
        self.assertEqual(
            rows.count(),
            2,
            "the second approval overwrote the first requester notification",
        )

    def test_each_notification_links_to_its_own_request(self) -> None:
        first = self._request()
        second = self._request()
        self._decide(first)
        self._decide(second)

        links = set(
            Notification.objects.filter(recipient=self.requester).values_list(
                "link", flat=True
            )
        )
        self.assertEqual(
            links,
            {f"/requests/{first.id}/", f"/requests/{second.id}/"},
            "a requester was pointed at a request other than the one decided",
        )

    def test_the_reference_is_what_makes_the_title_distinct(self) -> None:
        req = self._request()
        self._decide(req)
        title = Notification.objects.get(recipient=self.requester).title
        self.assertIn(
            req.reference,
            title,
            "without the reference in the TITLE, notify_unread dedups the row away",
        )

    def test_a_read_notification_does_not_block_the_next_one(self) -> None:
        """Control: the partial-unique index only covers UNREAD rows."""
        first = self._request()
        self._decide(first)
        Notification.objects.filter(recipient=self.requester).update(is_read=True)
        second = self._request()
        self._decide(second)
        self.assertEqual(Notification.objects.filter(recipient=self.requester).count(), 2)
