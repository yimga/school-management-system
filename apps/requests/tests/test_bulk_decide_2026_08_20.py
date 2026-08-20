"""Six pending requests should cost one decision, not six page loads.

R6 of the dead-end spec. Approving access requests was one-at-a-time on a detail
page: six pending requests meant six navigations and six posts, for a decision
that is identical on every row. That is the "fewer clicks" complaint in its
purest form — the platform made the reader repeat work it could batch.

``bulk_decide`` applies one decision to every selected request in a single
atomic post. The interesting tests here are not the happy path; they are the
three ways a bulk endpoint goes wrong:

  * the id list arrives FROM THE CLIENT, so scoping must happen in the queryset
    or one school can decide another school's requests;
  * a stale page re-posted must not overturn a decision someone else has since
    made, so only PENDING rows are actionable;
  * an unbounded batch is a denial-of-service on your own workers.
"""

from __future__ import annotations

import uuid

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.requests.models import AccessRequest
from apps.schools.models import School, SchoolMembership


class BulkDecideTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Bulk {uid}", slug=f"bulk-{uid}", subdomain=f"bulk{uid}", is_active=True
        )
        self.other_school = School.objects.create(
            name=f"Other {uid}", slug=f"other-{uid}", subdomain=f"other{uid}", is_active=True
        )
        self.admin = User.objects.create_user(
            username=f"bulk_admin_{uid}", password="Test1234", role=User.Role.ADMIN
        )
        SchoolMembership.objects.create(
            user=self.admin, school=self.school, role=User.Role.ADMIN, is_primary=True
        )
        self.requester = User.objects.create_user(
            username=f"bulk_req_{uid}", password="Test1234", role=User.Role.TEACHER
        )
        self.client.force_login(self.admin)

    def _make(self, *, school=None, status=AccessRequest.Status.PENDING, n=1):
        rows = []
        for _ in range(n):
            rows.append(
                AccessRequest.objects.create(
                    reference=f"AR-{uuid.uuid4().hex[:8].upper()}",
                    request_type=AccessRequest.RequestType.choices[0][0],
                    status=status,
                    school=school or self.school,
                    requester=self.requester,
                )
            )
        return rows

    def _post(self, ids, action="APPROVED", **extra):
        payload = {"request_ids": [str(i) for i in ids], "action": action}
        payload.update(extra)
        return self.client.post(reverse("requests:bulk_decide"), payload, follow=True)

    def test_six_requests_are_approved_in_one_post(self):
        rows = self._make(n=6)
        self._post([r.id for r in rows])
        approved = AccessRequest.objects.filter(
            id__in=[r.id for r in rows], status=AccessRequest.Status.APPROVED
        ).count()
        self.assertEqual(approved, 6, "the whole selection should clear in one action")

    def test_another_schools_request_is_never_decided(self):
        """The id list is client-supplied — scoping must live in the queryset."""
        mine = self._make(n=1)[0]
        theirs = self._make(school=self.other_school, n=1)[0]
        self._post([mine.id, theirs.id])
        theirs.refresh_from_db()
        self.assertEqual(
            theirs.status,
            AccessRequest.Status.PENDING,
            "a request belonging to another school was decided by this tenant",
        )
        mine.refresh_from_db()
        self.assertEqual(mine.status, AccessRequest.Status.APPROVED)

    def test_an_already_decided_request_is_not_overturned(self):
        """A stale page re-posted must not undo someone else's decision."""
        settled = self._make(status=AccessRequest.Status.DENIED, n=1)[0]
        self._post([settled.id], action="APPROVED")
        settled.refresh_from_db()
        self.assertEqual(
            settled.status,
            AccessRequest.Status.DENIED,
            "a decision already taken was overwritten by a stale bulk post",
        )

    def test_an_unknown_action_changes_nothing(self):
        row = self._make(n=1)[0]
        self._post([row.id], action="DELETE_EVERYTHING")
        row.refresh_from_db()
        self.assertEqual(row.status, AccessRequest.Status.PENDING)

    def test_an_empty_selection_is_a_harmless_no_op(self):
        row = self._make(n=1)[0]
        self.client.post(
            reverse("requests:bulk_decide"), {"action": "APPROVED"}, follow=True
        )
        row.refresh_from_db()
        self.assertEqual(row.status, AccessRequest.Status.PENDING)

    def test_an_oversized_batch_is_refused(self):
        from apps.requests.views import _BULK_DECISION_CAP

        rows = self._make(n=3)
        padding = [uuid.uuid4() for _ in range(_BULK_DECISION_CAP)]
        self._post([r.id for r in rows] + padding)
        for row in rows:
            row.refresh_from_db()
            self.assertEqual(
                row.status,
                AccessRequest.Status.PENDING,
                "an over-cap batch must be refused wholesale, not partly applied",
            )

    def test_get_is_not_a_decision_channel(self):
        row = self._make(n=1)[0]
        self.client.get(reverse("requests:bulk_decide"))
        row.refresh_from_db()
        self.assertEqual(row.status, AccessRequest.Status.PENDING)

    def test_a_user_who_cannot_manage_requests_is_blocked(self):
        row = self._make(n=1)[0]
        self.client.force_login(self.requester)  # TEACHER — not a manager role
        self._post([row.id])
        row.refresh_from_db()
        self.assertEqual(
            row.status,
            AccessRequest.Status.PENDING,
            "a non-manager reached the bulk decision endpoint",
        )


class TheDashboardOffersTheBulkPathTests(TestCase):
    """The endpoint is only useful if the queue actually exposes it."""

    def test_the_dashboard_template_posts_to_the_bulk_endpoint(self):
        from pathlib import Path

        src = Path("templates/requests/dashboard.html").read_text(encoding="utf-8")
        self.assertIn("requests:bulk_decide", src, "the queue has no bulk path")
        self.assertIn('name="request_ids"', src, "rows are not selectable")
        self.assertIn('value="APPROVED"', src, "no approve-selected submit")

    def test_the_bulk_form_needs_no_javascript(self):
        """It must work on an offline box with a broken bundle."""
        from pathlib import Path

        src = Path("templates/requests/dashboard.html").read_text(encoding="utf-8")
        bulk = src[src.index("rmc-bulk-decide") :]
        self.assertNotIn("onclick", bulk, "an inline handler crept into the bulk form")
        self.assertNotIn("<script", bulk, "the bulk path must not depend on script")
