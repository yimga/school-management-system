"""Each concern needs its own bell entry.

``_send_in_app`` routes through ``Notification.objects.notify_unread``, which
``update_or_create``s on ``(recipient, title, is_read=False)``. That collapse is
right for the notifications it was written for -- "New message from Mr Smith"
should show the LATEST message, not accumulate one row per message.

``_dispatch_dsl_alert`` used a CONSTANT title, "Urgent safeguarding concern", for
every urgent concern at every school. So the second urgent disclosure of the day
did not add a bell entry: it overwrote the first one's message and link. A DSL
with two open urgent concerns could only ever click through to the most recent,
and the earlier child's disclosure was gone from the queue she works from.

The concern is still in the ledger and in ``dsl_inbox`` -- this loses the pointer,
not the record. For a child-protection queue that is still the wrong behaviour:
the bell is what tells her there is something to look at.

Titles now carry the concern's own reference, which is what makes them distinct
under that unique key.
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.accounts.models import User
from apps.finance.models import Notification
from apps.safeguarding.services import submit_concern_for_school
from apps.schools.models import School, SchoolMembership


class AlertTitleIsPerConcernTests(TestCase):
    def setUp(self):
        slug = f"sgttl-{uuid.uuid4().hex[:8]}"
        self.school = School.objects.create(
            name="Title School", slug=slug, subdomain=slug
        )
        self.reporter = User.objects.create_user(username=f"rep_{slug}", password="x")
        self.dsl = User.objects.create_user(username=f"dsl_{slug}", password="x")
        self.dsl.role = "ADMIN"
        self.dsl.save(update_fields=["role"])
        for user, role in ((self.reporter, "TEACHER"), (self.dsl, "ADMIN")):
            SchoolMembership.objects.create(user=user, school=self.school, role=role)

    def _submit(self, narrative):
        return submit_concern_for_school(
            school=School.objects.get(pk=self.school.pk),
            reporter_user_id=self.reporter.pk,
            # An URGENT category, so the alert actually fires.
            category_key="fgm",
            narrative=narrative,
        )

    def _bell(self):
        return Notification.objects.filter(recipient=self.dsl)

    def test_one_urgent_concern_rings_the_bell(self):
        # Calibration: if no notification is written at all, the assertion below
        # would "pass" on an empty queryset.
        first = self._submit("First disclosure.")
        self.assertEqual(self._bell().count(), 1)
        self.assertTrue(first.is_urgent, "fixture must use an URGENT category")

    def test_a_second_urgent_concern_does_not_overwrite_the_first(self):
        first = self._submit("First disclosure.")
        second = self._submit("Second disclosure.")

        self.assertNotEqual(first.concern_id, second.concern_id)
        self.assertEqual(
            self._bell().count(),
            2,
            "the second urgent concern replaced the first one's bell entry, so the "
            "DSL can no longer reach the earlier child's disclosure",
        )

    def test_each_bell_entry_links_to_its_own_concern(self):
        first = self._submit("First disclosure.")
        second = self._submit("Second disclosure.")

        links = " ".join(self._bell().values_list("link", flat=True))
        self.assertIn(first.concern_id, links)
        self.assertIn(second.concern_id, links)
