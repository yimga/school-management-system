"""G6: cloud->box was poll-bound, so a cloud write waited out the cadence.

The appliance is behind NAT — the cloud can never open a connection to it — so every
transfer is box-initiated and a change made on the cloud is invisible until the box next
asks. The adaptive cadence deliberately BACKS OFF on a quiet school, so an idle box can
sit minutes behind. For a bursar issuing a receipt while a parent waits at the desk, that
is the difference between a system people trust and one they stop using.

The long-poll answers the moment a change exists. It carries NO row data — the box then
runs its ordinary sync cycle — so every cursor, policy, referential and replay guarantee
is untouched by it, and killing the feed degrades to exactly today's cadence.

Waits here are kept to a second or less: what is being proven is the DECISION (does it
answer, when, and on what evidence), not the wall-clock hold.
"""
from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from apps.academics.models import Department
from apps.accounts.models import User
from apps.api.sync_changes_api import SyncChangesFeedView, _database_has_changes
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.change_beacon import bump, last_change
from apps.sync_engine.edge_outbox import mint_edge_credential
from apps.sync_engine.tombstones import record_tombstone


class ChangeBeaconTests(TestCase):
    def setUp(self):
        cache.clear()
        uid = uuid.uuid4().hex[:6]
        self.school = School.objects.create(
            name=f"Beacon {uid}", slug=f"beacon-{uid}", subdomain=f"beacon{uid}"
        )

    def test_an_unknown_school_reports_no_information_not_no_changes(self):
        """`None` must never be read as an answer, or a cold cache would look like
        silence and the box would wait out a full hold for a change already sitting there."""
        self.assertIsNone(last_change(self.school.pk))

    def test_saving_a_synced_row_bumps_the_beacon(self):
        Department.objects.create(school=self.school, name="B", code=f"B-{uuid.uuid4().hex[:5]}")
        self.assertIsNotNone(last_change(self.school.pk))

    def test_deleting_a_synced_row_bumps_the_beacon(self):
        dept = Department.objects.create(
            school=self.school, name="C", code=f"C-{uuid.uuid4().hex[:5]}"
        )
        # The beacon COALESCES writes per school for half a second, so creating the row
        # above already claimed this school's slot. Clearing the cache without clearing
        # that in-process memory would test the coalescing, not the delete.
        from apps.sync_engine import change_beacon

        cache.clear()
        change_beacon.reset()
        dept.delete()
        self.assertIsNotNone(last_change(self.school.pk))

    def test_the_beacon_is_per_school(self):
        other = School.objects.create(name="Oth", slug="oth-bc", subdomain="othbc")
        bump(self.school.pk)
        self.assertIsNotNone(last_change(self.school.pk))
        self.assertIsNone(last_change(other.pk))


class DatabaseSweepTests(TestCase):
    """The safety net: correct even where the cache is per-process."""

    def setUp(self):
        cache.clear()
        uid = uuid.uuid4().hex[:6]
        self.school = School.objects.create(
            name=f"Sweep {uid}", slug=f"sweep-{uid}", subdomain=f"sweep{uid}"
        )

    def test_a_new_row_is_a_change(self):
        marker = timezone.now()
        self.assertFalse(_database_has_changes(self.school, marker))
        Department.objects.create(school=self.school, name="S", code=f"S-{uuid.uuid4().hex[:5]}")
        self.assertTrue(_database_has_changes(self.school, marker))

    def test_a_DELETION_is_a_change(self):
        """Omitting tombstones would make the feed answer "nothing new" for the one kind
        of change an operator most needs propagated quickly."""
        marker = timezone.now()
        self.assertFalse(_database_has_changes(self.school, marker))
        record_tombstone(self.school.id, "department", 4242, deleted_at=timezone.now())
        self.assertTrue(_database_has_changes(self.school, marker))

    def test_another_school_s_change_is_not_mine(self):
        other = School.objects.create(name="Oth", slug="oth-sw", subdomain="othsw")
        marker = timezone.now()
        Department.objects.create(school=other, name="X", code=f"X-{uuid.uuid4().hex[:5]}")
        self.assertFalse(_database_has_changes(self.school, marker))


@override_settings(RMC_SYNC_CHANGES_FEED_POLL_STEP_SECONDS=0.05)
class ChangesFeedEndpointTests(TestCase):
    def setUp(self):
        cache.clear()
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Feed {uid}", slug=f"feed-{uid}", subdomain=f"feed{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"feed_{uid}", password="Test1234", email=f"f{uid}@t.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        self.token, _obj = mint_edge_credential(
            self.school, self.user, device_id="feed-box", days=30
        )
        self.rf = APIRequestFactory()

    def _get(self, since=None, wait=0, auth=True):
        # urlencode, not string concatenation: an ISO timestamp ends in "+00:00" and a
        # raw "+" in a query string decodes to a SPACE, which the server then rightly
        # refuses as an unparseable `since`. The box's own client
        # (edge_outbox.wait_for_changes) encodes for exactly this reason.
        from urllib.parse import urlencode

        params = {"wait": wait}
        if since:
            params["since"] = since.isoformat()
        extra = {"HTTP_AUTHORIZATION": f"Bearer {self.token}"} if auth else {}
        request = self.rf.get("/api/v1/sync/changes/?" + urlencode(params), **extra)
        return SyncChangesFeedView.as_view()(request)

    def test_an_existing_change_is_answered_immediately(self):
        """The first answer comes from the database, so a change already sitting there is
        never delayed by an empty cache."""
        marker = timezone.now()
        Department.objects.create(school=self.school, name="Q", code=f"Q-{uuid.uuid4().hex[:5]}")
        resp = self._get(since=marker, wait=5)
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.data["changed"])
        self.assertLess(resp.data["waited_seconds"], 1.0)

    def test_nothing_new_returns_a_clean_negative_after_the_hold(self):
        """An expiring hold must be a plain 200, not a reset the box has to tell apart
        from being offline."""
        resp = self._get(since=timezone.now(), wait=1)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["changed"])

    def test_the_feed_never_returns_row_data(self):
        """It is a latency optimisation, not a transport. If it ever shipped rows it would
        need its own cursor, conflict and replay handling — a second sync engine."""
        Department.objects.create(school=self.school, name="R", code=f"R-{uuid.uuid4().hex[:5]}")
        resp = self._get(wait=0)
        self.assertEqual(set(resp.data) & {"rows", "changes", "data"}, set())

    def test_an_unauthenticated_caller_is_refused(self):
        resp = self._get(wait=0, auth=False)
        self.assertIn(resp.status_code, (401, 403))

    def test_a_malformed_since_is_rejected_rather_than_ignored(self):
        """Ignoring it would silently mean "since the beginning of time", so every poll
        would answer "changed" and the box would cycle in a loop."""
        request = self.rf.get(
            "/api/v1/sync/changes/?since=not-a-date&wait=0",
            HTTP_AUTHORIZATION=f"Bearer {self.token}",
        )
        resp = SyncChangesFeedView.as_view()(request)
        self.assertEqual(resp.status_code, 400)

    @override_settings(RMC_SYNC_CHANGES_FEED_ENABLED=False)
    def test_a_disabled_feed_tells_the_box_to_fall_back(self):
        """`supported: false` is a working deployment, not an error — the box reverts to
        the cadence rather than treating the cloud as broken."""
        resp = self._get(wait=0)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.data["supported"])
        self.assertTrue(resp.data["changed"])

    @override_settings(RMC_SYNC_CHANGES_FEED_MAX_WAIT_SECONDS=1)
    def test_the_hold_is_capped_by_the_server_not_the_caller(self):
        """A caller asking for a ten-minute hold would pin a worker."""
        resp = self._get(since=timezone.now(), wait=600)
        self.assertLessEqual(resp.data["waited_seconds"], 3.0)
