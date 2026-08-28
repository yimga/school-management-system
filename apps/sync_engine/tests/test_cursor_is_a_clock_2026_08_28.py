"""What the cursor overlap buys, and precisely where it stops.

CORRECTION, kept because it is the point. A first pass at this called
`build_edge_delta_rows(since=...)` directly and concluded the rail loses rows to
timestamp ties and to the commit-after-read race. It does not: no cycle asks the
builder from the stored high-water. `get_sync_cursor_for_request` subtracts an overlap
first, and its docstring already named both holes. Testing the builder in isolation
measured a component nothing calls that way.

So these tests go through the function the runner uses, and they pin three things: the
overlap closes the tie case, it closes the commit-after-read race for any transaction
shorter than the window, and it does NOT close it for one that runs longer. That last
is the residual the trade was made with open eyes -- a sequence written in the same
transaction as the business row is what would close it, at the cost of a migration on
every tenant table on the rail.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone


class TheClockCursorTests(TestCase):
    def setUp(self):
        from apps.academics.models import AcademicYear
        from apps.schools.models import School

        uid = uuid.uuid4().hex[:8]
        self.school = School.objects.create(
            name=f"Cur {uid}", slug=f"cur-{uid}", subdomain=f"cur{uid}", is_active=True
        )
        self.year = AcademicYear.objects.create(
            school=self.school, name="2026/2027",
            start_date="2026-09-01", end_date="2027-07-31",
        )

    def _stamp(self, model, pks, when):
        """Force updated_at, bypassing auto_now -- which is what a bulk write looks like."""
        model.objects.filter(pk__in=pks).update(updated_at=when)

    def _rows_raw(self, since=None):
        """The builder in isolation -- NOT how any cycle calls it."""
        from apps.sync_engine.edge_outbox import build_edge_delta_rows

        return build_edge_delta_rows(self.school, since=since, entities=["subject"])

    def _rows_as_a_cycle_would(self, direction=None):
        """Through `get_sync_cursor_for_request`, which is what the runner uses."""
        from apps.sync_engine.edge_outbox import build_edge_delta_rows
        from apps.sync_engine.models import EdgeSyncCursor, get_sync_cursor_for_request

        since = get_sync_cursor_for_request(self.school, direction or EdgeSyncCursor.PUSH)
        return build_edge_delta_rows(self.school, since=since, entities=["subject"])

    def _record_cursor(self, value, direction=None):
        from apps.sync_engine.models import EdgeSyncCursor, set_sync_cursor

        set_sync_cursor(self.school, direction or EdgeSyncCursor.PUSH, value)

    def _subjects(self, n, when):
        from apps.academics.models import Subject

        made = []
        for i in range(n):
            made.append(
                Subject.objects.create(school=self.school, name=f"SUBJ {i} {uuid.uuid4().hex[:6]}")
            )
        self._stamp(Subject, [s.pk for s in made], when)
        return made

    def test_the_overlap_recovers_a_tie_split_across_a_page(self):
        """Five rows share one stamp. Ship two, record that stamp, ask again.

        The RAW builder loses the other three -- `__gt` cannot resume inside a group of
        equal timestamps, and the builder's own docstring calls the last row of a page a
        safe cursor because "everything older has already been sent". Older is not EQUAL.
        A cycle does not ask that way, so the three come back.
        """
        when = timezone.now() - timedelta(minutes=5)
        self._subjects(5, when)

        rows, _meta = self._rows_raw()
        self.assertEqual(len(rows), 5)
        page_end = timezone.datetime.fromisoformat(rows[1]["updated_at"])

        # what the builder alone would do
        stranded, _m = self._rows_raw(since=page_end)
        self.assertEqual(len(stranded), 0)

        # what a cycle actually does
        self._record_cursor(page_end)
        recovered, _m = self._rows_as_a_cycle_would()
        self.assertEqual(len(recovered), 5)

    def test_the_overlap_recovers_a_commit_that_lands_behind_the_cursor(self):
        """A transaction that starts before a cycle reads the cursor and commits after it
        stamps an updated_at already behind the recorded position. Inside the overlap
        window the next cycle still offers it.
        """
        now = timezone.now()
        self._subjects(1, now)
        self._record_cursor(now)

        late = self._subjects(1, now - timedelta(seconds=30))
        self.assertTrue(late)

        offered, _m = self._rows_as_a_cycle_would()
        self.assertEqual(len(offered), 2)

    def test_a_transaction_LONGER_than_the_overlap_is_still_lost(self):
        """THE RESIDUAL, and the reason a monotonic sequence is the only complete answer.

        The overlap is a bound, not a proof. A transaction open longer than the window
        stamps a row far enough behind the cursor that even the re-ask misses it, and
        nothing reports it -- the scan simply never matches it again. Closing this needs
        a position written in the SAME transaction as the business row, which is a
        migration on every tenant table on the rail. Pinned so the bound stays a stated
        limit rather than an assumption nobody rechecks.
        """
        from apps.sync_engine.models import cursor_overlap_seconds

        overlap = cursor_overlap_seconds()
        self.assertGreater(overlap, 0, "no overlap configured: this test proves nothing")

        now = timezone.now()
        self._subjects(1, now)
        self._record_cursor(now)

        self._subjects(1, now - timedelta(seconds=overlap * 3))

        offered, _m = self._rows_as_a_cycle_would()
        # only the first row comes back; the long-transaction row never will.
        self.assertEqual(len(offered), 1)

    def test_the_overlap_is_configurable_and_defaults_to_a_real_window(self):
        # A zero overlap silently restores both holes, so the default has to be non-zero
        # and the value has to be inspectable rather than buried.
        from apps.sync_engine.models import cursor_overlap_seconds

        self.assertGreaterEqual(cursor_overlap_seconds(), 60)
        with self.settings(RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS=0):
            self.assertEqual(cursor_overlap_seconds(), 0)

    def test_the_cursor_is_still_a_clock(self):
        """Names what the position IS, so item 3 has a starting fact rather than a memory.

        A datetime is a local opinion: the two nodes' cursors are not commensurable, and
        a clock that steps backwards puts new rows below the mark.
        """
        from apps.sync_engine.models import EdgeSyncCursor

        field = EdgeSyncCursor._meta.get_field("high_water")
        self.assertEqual(field.get_internal_type(), "DateTimeField")
