"""A healthy box must leave a trace, or the Sync Center can never show it working.

A live tenant's Sync Center showed five consecutive ``Failed`` cycles, all
``pushed 0, pulled 0``, none newer than two days old -- while the same panel
reported the box had collected a queued full resync THAT MORNING. Both statements
were true, and together they were unreadable.

The cause is what the cloud records. It stamps a cycle on an inbound push, and on
a pull ONLY when a directive happened to ride along:

    directive = claim_pending_directive(school)
    if directive is not None:
        record_observed_cycle(school, ok=True, pulled=...)   # <- inside the if

So an ordinary successful pull -- the overwhelmingly common case, a box polling
every few minutes with nothing to push -- recorded NOTHING. A perfectly healthy
box is invisible, and the panel keeps showing whatever last went wrong, forever.

The fix moves the recording out of the directive branch: every served bundle is a
real cloud<->box transfer and is recorded as one. The directive, when present,
becomes detail on that record rather than the reason it exists.
"""

from __future__ import annotations

import uuid

from django.test import TestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.accounts.models import User
from apps.api.sync_bundle_api import SyncBundleDownloadView
from apps.people.models import StudentProfile
from apps.schools.models import School, SchoolMembership
from apps.sync_engine.edge_outbox import BUNDLE_CONTENT_TYPE
from apps.sync_engine.models import EdgeSyncRun

_SIGN_KEY = "edge-pull-recording-test-key"


@override_settings(RMC_SYNC_BUNDLE_SIGNING_KEY=_SIGN_KEY)
class SuccessfulPullIsRecordedTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Rec {uid}", slug=f"rec-{uid}", subdomain=f"rec{uid}", is_active=True
        )
        self.user = User.objects.create_superuser(
            username=f"rec_admin_{uid}", password="Test1234", email=f"r{uid}@test.com"
        )
        SchoolMembership.objects.create(
            user=self.user, school=self.school, role="ADMIN", is_primary=True
        )
        StudentProfile.objects.create(
            school=self.school, first_name="Ada", last_name="Njoya", date_of_birth="2012-01-01"
        )
        self.rf = APIRequestFactory()

    def _download(self):
        request = self.rf.get("/api/v1/sync/bundle/download/", HTTP_ACCEPT=BUNDLE_CONTENT_TYPE)
        request.school = self.school
        force_authenticate(request, user=self.user)
        return SyncBundleDownloadView.as_view()(request)

    def _runs(self):
        return EdgeSyncRun.objects.filter(school=self.school).order_by("-id")

    def test_an_ordinary_pull_records_a_cycle(self):
        """No directive pending — the common case, and it recorded nothing."""
        self.assertEqual(self._runs().count(), 0)
        resp = self._download()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            self._runs().count(),
            1,
            "a successful pull left no trace, so a healthy box looks idle forever",
        )
        run = self._runs().first()
        self.assertTrue(run.ok, "a served bundle is a successful transfer")

    def test_the_recorded_cycle_carries_the_row_count(self):
        self._download()
        run = self._runs().first()
        self.assertGreaterEqual(int(run.pulled or 0), 1, "the student row was not counted")

    def test_a_directive_pull_still_records_and_says_so(self):
        from apps.sync_engine.models import EdgeSyncDirective

        EdgeSyncDirective.objects.create(school=self.school, kind="full_resync")
        resp = self._download()
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self._runs().count(), 1, "the directive pull must record exactly once")
        run = self._runs().first()
        self.assertTrue(run.ok)
        self.assertIn(
            "full_resync",
            run.message or "",
            "the served directive should be detail on the record",
        )

    def test_two_pulls_record_two_cycles(self):
        """Consecutive polls must each register, so 'last sync' stays current."""
        self._download()
        self._download()
        self.assertEqual(self._runs().count(), 2)


class RecentCyclesShowTheReasonTests(TestCase):
    """The stored reason must reach the page. Five unexplained 'Failed' lines is the bug."""

    def test_the_template_renders_the_failure_reason(self):
        """Follows the cycle list to its new home rather than being deleted with the old.

        On 2026-08-21 "recent cycles" stopped being two lists. It had been rendered TWICE
        -- a server-rendered <ul data-rmc-sync-recent> in one card and a JS-polled table
        in another -- so one of the two was always stale. They are now one timeline in
        `_sync_activity.html`, and the assertion that matters is unchanged: a cycle that
        failed has to carry WHY, or five consecutive "Failed" lines tell a school nothing
        it can act on.
        """
        from pathlib import Path

        src = Path("templates/siteconfig/partials/_sync_activity.html").read_text(
            encoding="utf-8"
        )
        block = src
        self.assertIn("rmc-sc-timeline", block)
        self.assertTrue(
            ("run.error" in block) or ("run.message" in block),
            "The activity timeline renders 'Failed' and discards the stored reason, so a "
            "school cannot tell a real sync failure from a no-op it can ignore",
        )

    def test_the_live_timeline_also_carries_the_reason(self):
        """The server-rendered list is the first paint; the poll replaces it.

        Retiring the duplicate <ul> means the JS renderer is now the ONLY thing drawing
        cycles after the first second, so it has to carry the reason too -- otherwise the
        page shows why a cycle failed until the first poll and then quietly stops.
        """
        from pathlib import Path

        src = Path("static/js/rmc-sync-center.js").read_text(encoding="utf-8")
        block = src.split("function paintTimeline")[1][:3000]
        self.assertIn("run.error", block)
        self.assertIn("rmc-sc-timeline__detail", block)
