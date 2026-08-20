"""G2: a wall-clock cursor can skip a change, and nothing notices.

``build_edge_delta_rows`` selects ``updated_at__gt=cursor``. That is not a transactional
outbox, and it loses writes in two ways that are invisible when they happen:

  1. **The commit-after-read race.** A transaction that STARTS before a cycle reads the
     high-water but COMMITS after it stamps an ``updated_at`` that is already behind the
     recorded position. The next cycle asks for everything strictly newer, so the row is
     never offered again. Not delayed — lost, until something unrelated touches it.
  2. **Ties at a page boundary.** Two rows written inside the same clock tick, split
     across a page: the cursor advances onto that timestamp and ``__gt`` then excludes the
     twin that has not shipped.

Re-asking from slightly BEHIND the stored cursor closes both for any transaction shorter
than the overlap. The bound is real and is asserted here rather than glossed: a
transaction open longer than the window can still slip through, and only a monotonic
sequence written in the same transaction as the business row would close it completely —
which would cost a migration on fifteen live tenant tables.
"""
from __future__ import annotations

import datetime as dt
import uuid

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.academics.models import Department
from apps.schools.models import School
from apps.sync_engine.edge_outbox import build_edge_delta_rows
from apps.sync_engine.models import (
    EdgeSyncCursor,
    cursor_overlap_seconds,
    get_sync_cursor,
    get_sync_cursor_for_request,
    set_sync_cursor,
)


class CursorOverlapTests(TestCase):
    def setUp(self):
        uid = uuid.uuid4().hex[:6]
        self.school = School.objects.create(
            name=f"Cur {uid}", slug=f"cur-{uid}", subdomain=f"cur{uid}"
        )

    def test_the_request_position_sits_behind_the_stored_cursor(self):
        now = timezone.now()
        set_sync_cursor(self.school, EdgeSyncCursor.PULL, now)

        stored = get_sync_cursor(self.school, EdgeSyncCursor.PULL)
        asked = get_sync_cursor_for_request(self.school, EdgeSyncCursor.PULL)
        self.assertEqual(stored, now)
        self.assertEqual((stored - asked).total_seconds(), cursor_overlap_seconds())

    def test_no_cursor_still_means_everything(self):
        self.assertIsNone(get_sync_cursor_for_request(self.school, EdgeSyncCursor.PULL))

    @override_settings(RMC_EDGE_SYNC_CURSOR_OVERLAP_SECONDS=0)
    def test_zero_overlap_restores_the_previous_behaviour_exactly(self):
        now = timezone.now()
        set_sync_cursor(self.school, EdgeSyncCursor.PUSH, now)
        self.assertEqual(get_sync_cursor_for_request(self.school, EdgeSyncCursor.PUSH), now)

    def test_a_write_that_landed_behind_the_cursor_is_still_delivered(self):
        """The commit-after-read race, reproduced by writing a row whose updated_at is
        BEHIND an already-recorded cursor — exactly what a transaction that commits late
        leaves behind."""
        cursor_at = timezone.now()
        set_sync_cursor(self.school, EdgeSyncCursor.PUSH, cursor_at)

        late = Department.objects.create(school=self.school, name="Late", code="LATE-1")
        Department.objects.filter(pk=late.pk).update(
            updated_at=cursor_at - dt.timedelta(seconds=30)
        )

        strict, _meta = build_edge_delta_rows(self.school, since=cursor_at)
        self.assertNotIn(
            late.pk, [r["id"] for r in strict],
            "premise check: a strict cursor is supposed to miss this row",
        )

        overlapped, _meta = build_edge_delta_rows(
            self.school, since=get_sync_cursor_for_request(self.school, EdgeSyncCursor.PUSH)
        )
        self.assertIn(
            late.pk, [r["id"] for r in overlapped],
            "the row committed behind the cursor was lost, not delayed",
        )

    def test_a_row_sharing_the_cursor_timestamp_is_re_offered(self):
        """The page-boundary tie: `__gt` excludes the twin that shares the timestamp."""
        stamp = timezone.now()
        twin = Department.objects.create(school=self.school, name="Twin", code="TWIN-1")
        Department.objects.filter(pk=twin.pk).update(updated_at=stamp)
        set_sync_cursor(self.school, EdgeSyncCursor.PUSH, stamp)

        strict, _ = build_edge_delta_rows(self.school, since=stamp)
        self.assertNotIn(twin.pk, [r["id"] for r in strict])

        overlapped, _ = build_edge_delta_rows(
            self.school, since=get_sync_cursor_for_request(self.school, EdgeSyncCursor.PUSH)
        )
        self.assertIn(twin.pk, [r["id"] for r in overlapped])

    def test_the_bound_is_stated_honestly(self):
        """A transaction open LONGER than the overlap is still missed. Asserting the limit
        keeps the docstring from drifting into a promise the mechanism does not make."""
        cursor_at = timezone.now()
        set_sync_cursor(self.school, EdgeSyncCursor.PUSH, cursor_at)
        very_late = Department.objects.create(school=self.school, name="VLate", code="VL-1")
        Department.objects.filter(pk=very_late.pk).update(
            updated_at=cursor_at - dt.timedelta(seconds=cursor_overlap_seconds() + 60)
        )
        rows, _ = build_edge_delta_rows(
            self.school, since=get_sync_cursor_for_request(self.school, EdgeSyncCursor.PUSH)
        )
        self.assertNotIn(very_late.pk, [r["id"] for r in rows])

    def test_the_overlap_never_rewinds_the_stored_cursor(self):
        """Re-asking is a READ position. Persisting it would rewind real progress and
        turn a bounded re-ship into an unbounded one."""
        now = timezone.now()
        set_sync_cursor(self.school, EdgeSyncCursor.PULL, now)
        get_sync_cursor_for_request(self.school, EdgeSyncCursor.PULL)
        self.assertEqual(get_sync_cursor(self.school, EdgeSyncCursor.PULL), now)


class OverlapCostTests(TestCase):
    """The overlap must not be paid for in bandwidth, rewrites, or invented conflicts.

    Re-offering recent rows is the price of closing the commit-after-read race. Charged
    naively it would undo three things this engine already got right, and each of those
    is a bug that ALSO existed before the overlap — a retried cycle after any failure
    re-offers rows too. The overlap only made them routine.
    """

    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        uid = uuid.uuid4().hex[:6]
        self.school = School.objects.create(
            name=f"Cost {uid}", slug=f"cost-{uid}", subdomain=f"cost{uid}"
        )
        from apps.accounts.models import User

        self.admin = User.objects.create_user(
            username=f"cost_{uid}", password="x" * 12, role=User.Role.ADMIN, is_staff=True
        )
        self.dept = Department.objects.create(
            school=self.school, name="Ops", code=f"OPS-{uid}"
        )

    def test_a_row_already_delivered_is_not_re_sent(self):
        from apps.sync_engine import push_ledger

        rows, _meta = build_edge_delta_rows(self.school)
        self.assertTrue(rows)
        push_ledger.record_sent(self.school, rows)

        memory = push_ledger.recent_sent(self.school)
        again, _meta = build_edge_delta_rows(self.school)
        self.assertEqual(
            [r for r in again if not push_ledger.already_sent(memory, r)],
            [],
            "the overlap re-transmitted rows the last cycle already delivered",
        )

    def test_a_genuine_edit_after_delivery_still_ships(self):
        from apps.sync_engine import push_ledger

        rows, _meta = build_edge_delta_rows(self.school)
        push_ledger.record_sent(self.school, rows)

        self.dept.name = "Ops renamed"
        self.dept.save(update_fields=["name", "updated_at"])

        memory = push_ledger.recent_sent(self.school)
        again, _meta = build_edge_delta_rows(self.school)
        fresh = [r for r in again if not push_ledger.already_sent(memory, r)]
        self.assertEqual([r["id"] for r in fresh], [self.dept.pk])

    def test_a_full_resync_forgets_what_was_already_sent(self):
        """Otherwise "send everything again" would send nothing at all."""
        from apps.sync_engine import push_ledger

        rows, _meta = build_edge_delta_rows(self.school)
        push_ledger.record_sent(self.school, rows)
        push_ledger.reset(self.school)
        self.assertEqual(push_ledger.recent_sent(self.school), {})

    def test_a_row_with_no_timestamp_is_never_suppressed(self):
        from apps.sync_engine import push_ledger

        memory = {"department|1|": "2026-08-20T00:00:00+00:00"}
        self.assertFalse(
            push_ledger.already_sent(memory, {"entity_type": "department", "id": 1})
        )

    def test_re_applying_an_identical_row_does_not_touch_the_record(self):
        """A save that changes nothing still bumps updated_at, which re-enters the row
        into the delta in the OTHER direction — churn the engine manufactures itself."""
        from apps.api.sync_services import apply_changes

        before = Department.objects.get(pk=self.dept.pk).updated_at
        out = apply_changes(
            str(self.school.id), self.admin,
            [{
                "entity_type": "department", "id": self.dept.pk, "client_offline_id": "",
                "changes": {"name": self.dept.name},
                "updated_at": (before + dt.timedelta(minutes=1)).isoformat(),
            }],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        self.assertEqual(out["results"][0]["data"].get("unchanged"), True)
        self.assertEqual(Department.objects.get(pk=self.dept.pk).updated_at, before)

    def test_a_retried_pull_does_not_invent_a_conflict_out_of_its_own_write(self):
        """After applying a pulled row, THIS side's updated_at is newer than the cloud's.
        Re-offering the row then graded the engine's own write as a local edit and raised
        a SyncConflict — asking an operator to adjudicate between a value and itself."""
        from apps.api.sync_services import apply_changes
        from apps.siteconfig.models import SyncConflict

        # The cloud's row must be NEWER than the box's copy for the first apply to land
        # at all — otherwise this test would be exercising ordinary LWW, not the retry.
        row = {
            "entity_type": "department", "id": self.dept.pk, "client_offline_id": "",
            "changes": {"name": "From the cloud"},
            "updated_at": (timezone.now() + dt.timedelta(minutes=5)).isoformat(),
        }
        first = apply_changes(
            str(self.school.id), self.admin, [row],
            persist_conflicts=True, sync_origin="cloud-pull",
        )
        self.assertEqual(first["results"][0]["status"], 200, first["results"])

        second = apply_changes(
            str(self.school.id), self.admin, [row],
            persist_conflicts=True, sync_origin="cloud-pull",
        )
        self.assertEqual(second["conflicts"], [], "a retry manufactured a conflict")
        self.assertEqual(
            SyncConflict.objects.filter(school=self.school).count(), 0
        )

    def test_a_REAL_local_edit_after_a_pull_is_still_a_conflict(self):
        """The guard above must not swallow genuine divergence: once a human edits the
        row locally, an older cloud value is a real conflict again."""
        from apps.api.sync_services import apply_changes

        apply_changes(
            str(self.school.id), self.admin,
            [{
                "entity_type": "department", "id": self.dept.pk, "client_offline_id": "",
                "changes": {"name": "From the cloud"},
                "updated_at": (timezone.now() + dt.timedelta(minutes=5)).isoformat(),
            }],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        local = Department.objects.get(pk=self.dept.pk)
        local.name = "Edited here by a human"
        local.save(update_fields=["name", "updated_at"])

        out = apply_changes(
            str(self.school.id), self.admin,
            [{
                "entity_type": "department", "id": self.dept.pk, "client_offline_id": "",
                "changes": {"name": "Stale cloud value"},
                "updated_at": (timezone.now() - dt.timedelta(minutes=5)).isoformat(),
            }],
            persist_conflicts=False, sync_origin="cloud-pull",
        )
        self.assertEqual(out["results"][0]["status"], 409)
        self.assertEqual(out["results"][0]["data"]["error"], "conflict")


class NoOpDetectionIsConservativeTests(TestCase):
    """The skip-the-redundant-write check must never be able to change an outcome.

    Caught by an EXISTING test on 2026-08-20, not by design: Django's
    ``BaseManager.__str__`` returns ``"<app>.<Model>.<name>"``, so a many-to-many
    attribute stringifies to something a wire value can genuinely equal. Comparing every
    attribute by text therefore declared a poisoned M2M write "unchanged" and returned a
    green 200 where the engine had always returned 422 — an optimisation quietly
    swallowing an error, which is worse than the redundant write it was avoiding.
    """

    def test_a_related_manager_is_never_reported_unchanged(self):
        from apps.api.sync_services import _same_value

        class _FakeManager:
            def __str__(self):
                return "accounts.User.None"

        self.assertFalse(_same_value(_FakeManager(), "accounts.User.None"))

    def test_a_model_instance_is_never_reported_unchanged(self):
        from apps.api.sync_services import _same_value

        school = School.objects.create(name="NoOp", slug="noop-x", subdomain="noopx")
        self.assertFalse(_same_value(school, str(school)))

    def test_plain_scalars_still_compare_across_the_wire_representation(self):
        """The comparison has to survive the round trip or it never fires: one side is a
        live model attribute, the other a JSON payload."""
        from decimal import Decimal

        from apps.api.sync_services import _same_value

        self.assertTrue(_same_value(Decimal("1.00"), "1.00"))
        self.assertTrue(_same_value(3, "3"))
        self.assertTrue(_same_value(True, "True"))
        self.assertTrue(_same_value(None, None))
        self.assertFalse(_same_value(None, "x"))
        self.assertFalse(_same_value("a", "b"))

    def test_a_date_compares_against_its_iso_form(self):
        from datetime import date

        from apps.api.sync_services import _same_value

        self.assertTrue(_same_value(date(2026, 9, 1), "2026-09-01"))
        self.assertFalse(_same_value(date(2026, 9, 1), "2026-09-02"))
