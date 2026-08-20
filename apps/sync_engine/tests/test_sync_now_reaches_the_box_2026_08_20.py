""""Sync now" has to actually reach a box that is sitting still. These pin the path.

THE HONEST ARCHITECTURE, restated because it is what makes this subtle: the box is
behind NAT, so the cloud can never open a connection to it. "Sync now" therefore
RECORDS a directive and the box collects it on its next call out. That is correct and
it is not going to change.

What was wrong was the LATENCY, and it was wrong in the exact case an operator hits:

  * the long-poll changes feed — the whole point of which is collapsing cloud->box from
    an interval to about a second — answered only on ROW changes. A directive is not a
    row change, so queueing a resync for a QUIET school woke nobody. The box stayed in
    its 25-second hold and the operator's click did nothing visible for minutes.
  * once the box finally collected the directive it rewound its cursors and then waited
    out the adaptive cadence before replaying — and that cadence deliberately BACKS OFF
    for a quiet box, which is precisely the box someone is resyncing.

Both are latency bugs, not data bugs; nothing here was ever lost. But "I pressed the
button and nothing happened" is how an operator concludes the feature does not work,
and this system already has one button that failed every time it was pressed.
"""
from __future__ import annotations

from unittest import mock

from django.test import SimpleTestCase, TestCase

from apps.sync_engine.models import (
    EdgeSyncDirective,
    claim_pending_directive,
    request_full_resync,
)


class DirectiveWakesTheChangesFeedTests(TestCase):
    def setUp(self):
        from apps.schools.models import School

        self.school = School.objects.create(
            name="Gilead Tech", slug="gilead-tech", subdomain="gilead-tech"
        )

    def _has_changes(self, since=None):
        from apps.api.sync_changes_api import _database_has_changes

        return _database_has_changes(self.school, since)

    def test_a_quiet_school_with_nothing_pending_reports_no_changes(self):
        """The baseline. If this is True the next test proves nothing."""
        self.assertFalse(self._has_changes())

    def test_a_pending_directive_counts_as_something_for_this_box(self):
        request_full_resync(self.school)
        self.assertTrue(self._has_changes())

    def test_a_served_directive_stops_counting(self):
        """Self-clearing: the download endpoint stamps served_at as it hands it over."""
        request_full_resync(self.school)
        claim_pending_directive(self.school)
        self.assertFalse(self._has_changes())

    def test_a_directive_is_not_filtered_by_the_data_cursor(self):
        """A directive has no place on the timeline the pull cursor tracks.

        Filtering it by ``since`` would hide exactly the directive queued for a school
        whose rows are all older than the box's cursor — a quiet school, again.
        """
        from django.utils import timezone

        request_full_resync(self.school)
        self.assertTrue(self._has_changes(since=timezone.now()))

    def test_queueing_a_resync_nudges_the_beacon(self):
        with mock.patch("apps.sync_engine.change_beacon.bump") as bumped:
            request_full_resync(self.school)
        self.assertTrue(bumped.called)

    def test_a_duplicate_click_still_nudges(self):
        """Collapsing duplicate directives must not also swallow the wake.

        An operator who clicks twice because nothing seemed to happen is the single
        most likely person to be waiting on this nudge.
        """
        request_full_resync(self.school)
        with mock.patch("apps.sync_engine.change_beacon.bump") as bumped:
            again = request_full_resync(self.school)
        self.assertTrue(bumped.called)
        self.assertEqual(
            EdgeSyncDirective.objects.filter(school=self.school).count(),
            1,
            "duplicate directives were created",
        )
        self.assertIsNotNone(again)

    def test_a_beacon_failure_never_breaks_queueing_the_directive(self):
        """The directive is the guarantee; the nudge is only ever an optimisation."""
        with mock.patch(
            "apps.sync_engine.change_beacon.bump", side_effect=RuntimeError("no cache")
        ):
            directive = request_full_resync(self.school)
        self.assertIsNotNone(directive)
        self.assertTrue(
            EdgeSyncDirective.objects.filter(
                school=self.school, served_at__isnull=True
            ).exists()
        )

    def test_a_broken_directive_lookup_never_breaks_the_feed(self):
        """The directive check is a bonus on top of the feed; it may never break it."""
        with mock.patch(
            "apps.sync_engine.models.EdgeSyncDirective.objects.filter",
            side_effect=RuntimeError("boom"),
        ):
            self.assertFalse(self._has_changes())


class ResyncRaisesAWakeTests(SimpleTestCase):
    """The rewind is instant; the replay must not then wait out the cadence."""

    def test_the_runner_raises_a_wake_after_rewinding(self):
        import inspect

        from apps.sync_engine import sync_runner

        source = inspect.getsource(sync_runner)
        self.assertIn("full-resync", source)
        after = source.split("reset_sync_cursors(school)", 1)[1][:1600]
        self.assertIn("request_wake", after)

    def test_the_wake_is_guarded(self):
        """A missed wake costs latency; it must never cost the cycle."""
        import inspect

        from apps.sync_engine import sync_runner

        source = inspect.getsource(sync_runner)
        after = source.split("request_wake", 1)[1][:400]
        self.assertIn("except Exception", after)
