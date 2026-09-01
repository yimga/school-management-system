"""Is the causal branch LIVE, and does a conflict on it actually converge?

WHAT WAS ALREADY TRUE, AND WHY IT DID NOTHING. ``sync_services._conflict_decision``
already accepted ``base_updated_at`` and already outranked the wall clock with it in both
directions. Nothing emitted one. The parameter was ``None`` on every row in the fleet, the
causal branch never executed, and the audit's headline failure - a box whose clock is
systematically ahead silently destroying a concurrent cloud edit - was still shipping. A
decision procedure nobody feeds is not a fix; it is a fix-shaped hole.

WHAT MAKES IT LIVE. ``SyncApplyLedger`` gains ``peer_updated_at``: the stamp the PEER's
row carried on the version this side actually applied. ``edge_outbox`` ships it as each
delta row's ``base_updated_at``. The receiver already knew what to do with it.

THE TRAP THIS FILE EXISTS TO KEEP CLOSED. The obvious cheaper design - derive causality
from the ledger's existing ``applied_updated_at`` - was considered and rejected, and the
reason is a failure mode strictly worse than the bug being fixed. That column is OUR
stamp, the ledger records applies and never pushes, and a CONFLICT is by definition not
applied, so the column never catches up. Resolving the conflict does not move it either:
``conflict_actions.resolve_sync_conflict_row`` writes the winning value with a bare
``save()`` and never touches the ledger. One legitimate edit would then conflict on every
cycle, for ever, with no operator action able to stop it - a permanently stuck row instead
of an occasional lost write.

THE SAME TRAP HAS A SECOND MOUTH, and it was found by running this file rather than by
reading the code. Once this side APPLIES the peer's row, ``auto_now`` moves our stamp to a
value the peer has never seen, and the reverse delta correctly suppresses that row as an
echo - so the peer is never told, its recorded base stays one version behind ours for
ever, and its very next edit arrives with a base that is legitimately older than our row.
``server_dt > base`` is then true on a row with no concurrent edit anywhere near it. The
guard in ``_apply_changes_inner`` closes it: if our row's current stamp is still exactly
what OUR OWN sync apply wrote, we have not moved independently and there is nothing to
adjudicate. :meth:`AConflictedRowConvergesTests
.test_a_conflicted_row_applies_on_the_next_cycle_and_keeps_applying` runs five full cycles
precisely because one cycle would have passed with that hole wide open.

So the load-bearing test here is not "does a concurrent edit conflict" (it does, and
``test_conflict_causality_2026_08_31`` already holds that at the unit level). It is
CONVERGENCE: a row that conflicts must, once a human resolves it, APPLY on the next cycle
and keep applying. :class:`AConflictedRowConvergesTests` drives real pushes and pulls
between two nodes through the real producer and the real apply path, and asserts the
negative control beside it - that the rejected design, fed the stamp it would have used,
still says "conflict" at the very moment the shipped design says "apply".
"""
from __future__ import annotations

import datetime as dt
import json
import uuid

from django.test import TestCase
from django.utils import timezone

from apps.api.sync_services import (
    _conflict_decision,
    _get_entity_config,
    apply_changes,
)
from apps.sync_engine.edge_outbox import build_edge_delta_rows
from apps.sync_engine.models import SyncApplyLedger

ENTITY = "academic_year"


def _school_and_user(prefix):
    """A school plus a superuser member of it.

    The subdomain is given explicitly and uniquely: it carries a UNIQUE index and blank
    is not exempt, so a second School created with the default would collide.
    """
    from apps.accounts.models import User
    from apps.schools.models import School, SchoolMembership

    uid = uuid.uuid4().hex[:8]
    school = School.objects.create(
        name=f"{prefix} {uid}",
        slug=f"{prefix}-{uid}",
        subdomain=f"{prefix}{uid}",
        is_active=True,
    )
    user = User.objects.create_superuser(
        username=f"{prefix}_{uid}", password="Test1234", email=f"{prefix}{uid}@t.com"
    )
    SchoolMembership.objects.create(
        user=user, school=school, role="ADMIN", is_primary=True
    )
    return school, user, uid


def _year(school, name):
    model, _allowed = _get_entity_config(include_derived=True)[ENTITY]
    return model.objects.create(
        school=school, name=name, start_date="2026-09-01", end_date="2027-07-31"
    )


def _over_the_wire(rows):
    """Exactly what ``export_delta_bundle`` does to a row body, and no more.

    ``json.dumps(row, default=str)`` then ``json.loads``. Handing the receiver live Python
    ``date``/``Decimal`` objects would test a wire that does not exist - and would hide the
    one thing that matters here, that an ISO string survives the trip and is parsed back
    into a datetime on arrival.
    """
    return [json.loads(json.dumps(row, default=str)) for row in rows]


def _ledger(school, pk):
    return SyncApplyLedger.objects.filter(
        school=school, entity_type=ENTITY, local_pk=str(pk)
    ).first()


def _force_stamp(model, pk, when):
    """Set ``updated_at`` to ``when``, bypassing ``auto_now``.

    A queryset ``.update()`` does not run field pre_save, which is the only way to stage
    the scenario the whole audit is about: an appliance whose clock is HOURS ahead of the
    cloud's. Every wall-clock rule on the rail hands that box the win; only causality can
    take it back. It is also how a row is aged, so an incoming stamp can be newer than a
    row created a microsecond ago by ``setUp``.
    """
    model._default_manager.filter(pk=pk).update(updated_at=when)


# --------------------------------------------------------------------------- #
# 1. The ledger now answers two questions, and keeps them apart
# --------------------------------------------------------------------------- #
class TheLedgerRecordsBothStampsTests(TestCase):
    """``applied_updated_at`` is OURS, ``peer_updated_at`` is THEIRS. Never merged."""

    def setUp(self):
        self.school, self.user, uid = _school_and_user("led")
        self.row = _year(self.school, f"Year {uid}")
        # Age our copy a day, so an incoming stamp from three hours ago is genuinely
        # newer and the wall-clock rules let it in. Without this every peer row loses to
        # a record created microseconds ago and nothing under test would ever run.
        _force_stamp(type(self.row), self.row.pk, timezone.now() - dt.timedelta(days=1))
        self.row.refresh_from_db()

    def _pull_one(self, changes, stamp, **extra):
        item = {
            "entity_type": ENTITY,
            "id": self.row.pk,
            "updated_at": stamp.isoformat() if stamp else None,
            "changes": changes,
        }
        item.update(extra)
        return apply_changes(
            self.school.id, self.user, [item], sync_origin="cloud-pull"
        )

    def test_an_applied_row_records_the_peer_stamp_not_only_the_local_one(self):
        peer_stamp = timezone.now() - dt.timedelta(hours=3)
        out = self._pull_one({"name": "Renamed by the cloud"}, peer_stamp)
        self.assertEqual(out["results"][0]["status"], 200, out["results"])

        entry = _ledger(self.school, self.row.pk)
        self.assertIsNotNone(entry, "no ledger row was written for an applied sync row")
        self.row.refresh_from_db()
        self.assertEqual(
            entry.applied_updated_at,
            self.row.updated_at,
            "the echo stamp must stay OUR post-write updated_at",
        )
        self.assertEqual(
            entry.peer_updated_at,
            peer_stamp,
            "the causality stamp must be THEIR version, not ours",
        )
        self.assertNotEqual(
            entry.applied_updated_at,
            entry.peer_updated_at,
            "the two stamps collapsed onto one value; they answer different questions",
        )

    def test_the_unchanged_short_circuit_records_the_peer_stamp_too(self):
        """The loop breaker. Nothing is written, but our row IS their version.

        This is the branch a resolved conflict lands on - both sides now hold the same
        content - and it is the only place the peer stamp can advance for a row nobody is
        going to write again. Without it, a resolved conflict re-conflicts for ever.
        """
        peer_stamp = timezone.now() - dt.timedelta(hours=3)
        out = self._pull_one({"name": self.row.name}, peer_stamp)
        self.assertEqual(out["results"][0]["status"], 200, out["results"])
        self.assertTrue(
            out["results"][0]["data"].get("unchanged"),
            "this test no longer exercises the unchanged short circuit",
        )
        entry = _ledger(self.school, self.row.pk)
        self.assertIsNotNone(entry)
        self.assertEqual(entry.peer_updated_at, peer_stamp)

    def test_a_peer_row_with_no_usable_stamp_clears_the_base_rather_than_keeping_a_stale_one(self):
        """``None`` is recorded as ``None``, never quietly left at the old value.

        A retained stamp would claim descent from a version we did not just take, which is
        the exact silent overwrite this column exists to stop. Driven through the
        unchanged short circuit because that is the one branch a row with no timestamp at
        all can legitimately reach.
        """
        first = timezone.now() - dt.timedelta(hours=3)
        self._pull_one({"name": "Renamed by the cloud"}, first)
        self.assertEqual(_ledger(self.school, self.row.pk).peer_updated_at, first)

        self.row.refresh_from_db()
        out = self._pull_one({"name": self.row.name}, None)
        self.assertEqual(out["results"][0]["status"], 200, out["results"])
        self.assertTrue(out["results"][0]["data"].get("unchanged"), out["results"])
        self.assertIsNone(
            _ledger(self.school, self.row.pk).peer_updated_at,
            "a stale peer stamp survived an apply that carried no version at all",
        )

    def test_a_refused_row_never_records_a_peer_stamp(self):
        """We did not take their version, so we may not later claim to descend from it."""
        first = timezone.now() - dt.timedelta(hours=3)
        self._pull_one({"name": "Cloud one"}, first)
        self.assertEqual(_ledger(self.school, self.row.pk).peer_updated_at, first)
        # A LOCAL edit moves us off our own apply, so the next incoming row is graded.
        _force_stamp(type(self.row), self.row.pk, timezone.now() + dt.timedelta(hours=6))

        stale = timezone.now() - dt.timedelta(hours=9)
        out = self._pull_one({"name": "Cloud two, arriving stale"}, stale)
        self.assertEqual(out["results"][0]["status"], 409, out["results"])
        self.assertEqual(
            _ledger(self.school, self.row.pk).peer_updated_at,
            first,
            "a REFUSED row advanced the causality stamp; the next push would claim "
            "descent from an edit this side never applied",
        )


# --------------------------------------------------------------------------- #
# 2. The producer emits it
# --------------------------------------------------------------------------- #
class TheProducerEmitsTheBaseVersionTests(TestCase):
    def setUp(self):
        self.school, self.user, uid = _school_and_user("prod")
        self.row = _year(self.school, f"Year {uid}")
        _force_stamp(type(self.row), self.row.pk, timezone.now() - dt.timedelta(days=1))
        self.row.refresh_from_db()
        self.peer_stamp = timezone.now() - dt.timedelta(hours=3)

    def _rows(self):
        rows, _meta = build_edge_delta_rows(self.school, entities=[ENTITY])
        return [r for r in rows if str(r.get("id")) == str(self.row.pk)]

    def _receive_from_the_peer(self, name="From the cloud"):
        out = apply_changes(
            self.school.id,
            self.user,
            [{
                "entity_type": ENTITY,
                "id": self.row.pk,
                "updated_at": self.peer_stamp.isoformat(),
                "changes": {"name": name},
            }],
            sync_origin="cloud-pull",
        )
        self.assertEqual(out["results"][0]["status"], 200, out["results"])

    def _edit_locally(self):
        """Move the row off its echo stamp so it actually reaches the wire."""
        self.row.refresh_from_db()
        self.row.name = "Edited locally afterwards"
        self.row.save(update_fields=["name", "updated_at"])

    def test_a_row_this_side_has_never_received_omits_the_key_entirely(self):
        """Absent means absent. A null would be a claim, and a claim we cannot back."""
        rows = self._rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertNotIn("base_updated_at", rows[0])

    def test_a_row_applied_from_the_peer_carries_their_stamp_as_its_base(self):
        self._receive_from_the_peer()
        self._edit_locally()
        rows = self._rows()
        self.assertEqual(len(rows), 1, rows)
        self.assertEqual(rows[0].get("base_updated_at"), self.peer_stamp.isoformat())

    def test_the_base_version_survives_json_serialisation(self):
        """The bundle body is ``json.dumps(row, default=str)``; a value that cannot
        serialise would not fail loudly here, it would ship as a repr nothing can parse."""
        from apps.api.sync_services import _parse_client_updated_at

        self._receive_from_the_peer()
        self._edit_locally()
        wire = _over_the_wire(self._rows())
        self.assertEqual(
            _parse_client_updated_at(wire[0]["base_updated_at"]), self.peer_stamp
        )

    def test_echo_suppression_is_not_broken_by_the_second_stamp(self):
        """The two stamps share a row; the echo question must still get the old answer."""
        self._receive_from_the_peer()
        self.assertEqual(
            self._rows(), [], "a pure echo is shipping back to its origin again"
        )
        self._edit_locally()
        self.assertEqual(len(self._rows()), 1, "a genuine local edit stopped shipping")

    def test_the_base_is_not_the_echo_stamp(self):
        """The one substitution that would rebuild the rejected design, caught head on."""
        self._receive_from_the_peer()
        self._edit_locally()
        entry = _ledger(self.school, self.row.pk)
        shipped = self._rows()[0]["base_updated_at"]
        self.assertEqual(shipped, self.peer_stamp.isoformat())
        self.assertNotEqual(
            shipped,
            entry.applied_updated_at.isoformat(),
            "the producer is shipping OUR stamp as the base version",
        )


# --------------------------------------------------------------------------- #
# 3. Mixed fleet
# --------------------------------------------------------------------------- #
class AnOlderBoxIsUnaffectedTests(TestCase):
    """A box built before this column sends no key. Nothing about it may change."""

    def setUp(self):
        self.school, self.user, uid = _school_and_user("mixed")
        self.row = _year(self.school, f"Year {uid}")

    def _push(self, **extra):
        item = {
            "entity_type": ENTITY,
            "id": self.row.pk,
            "updated_at": (timezone.now() + dt.timedelta(hours=6)).isoformat(),
            "changes": {"name": "Renamed by an old box"},
        }
        item.update(extra)
        return apply_changes(
            self.school.id, self.user, [item], sync_origin="edge-push"
        )

    def test_a_missing_key_never_raises_and_grades_by_the_wall_clock(self):
        out = self._push()
        self.assertEqual(out["results"][0]["status"], 200, out["results"])

    def test_an_explicit_null_is_treated_as_absent(self):
        """Some producer, some day, will send the key as null. It must mean 'no base'."""
        out = self._push(base_updated_at=None)
        self.assertEqual(out["results"][0]["status"], 200, out["results"])

    def test_an_unparseable_base_degrades_to_the_old_rules_rather_than_500ing(self):
        out = self._push(base_updated_at="not a timestamp")
        self.assertEqual(out["results"][0]["status"], 200, out["results"])

    def test_a_null_peer_column_produces_no_key_on_the_wire(self):
        """A ledger row written BEFORE the migration has a null peer stamp. That is the
        state of every existing row on every box in the fleet on upgrade day."""
        SyncApplyLedger.objects.create(
            school=self.school,
            entity_type=ENTITY,
            local_pk=str(self.row.pk),
            applied_updated_at=None,
            peer_updated_at=None,
            origin="cloud-pull",
        )
        rows, _meta = build_edge_delta_rows(self.school, entities=[ENTITY])
        mine = [r for r in rows if str(r.get("id")) == str(self.row.pk)]
        self.assertEqual(len(mine), 1, mine)
        self.assertNotIn("base_updated_at", mine[0])

    def test_the_tie_is_still_a_conflict(self):
        """The rule the previous pass added. Causality must not have loosened it."""
        now = timezone.now()
        self.assertEqual(_conflict_decision("student", "edge-push", now, now), "conflict")
        self.assertEqual(_conflict_decision("student", "cloud-pull", now, now), "conflict")


# --------------------------------------------------------------------------- #
# 4. CONVERGENCE - the load-bearing test
# --------------------------------------------------------------------------- #
class AConflictedRowConvergesTests(TestCase):
    """Two nodes, one row, the real producer and the real apply path on both legs.

    The box's clock is forced HOURS ahead throughout, so every wall-clock rule on the rail
    hands the box the win. Only causality can refuse it, and only a causality stamp that
    keeps advancing can ever let it back in.
    """

    def setUp(self):
        self.cloud_school, self.cloud_user, uid = _school_and_user("cld")
        self.box_school, self.box_user, _ = _school_and_user("box")
        self.model, _allowed = _get_entity_config(include_derived=True)[ENTITY]
        self.cloud_row = _year(self.cloud_school, f"Year {uid}")
        self.box_row = _year(self.box_school, f"Year {uid}")

    # -- the wire ---------------------------------------------------------- #
    def _cloud_delta(self):
        rows, _meta = build_edge_delta_rows(self.cloud_school, entities=[ENTITY])
        return [
            dict(r, id=self.box_row.pk)
            for r in _over_the_wire(rows)
            if str(r.get("id")) == str(self.cloud_row.pk)
        ]

    def _pull(self, *, required=True):
        """Cloud -> box. Returns ``(result, sent_row)``, or ``(None, None)`` when the
        cloud has nothing to serve - which is the correct answer whenever the cloud's copy
        is still exactly what sync last wrote there."""
        items = self._cloud_delta()
        if not items:
            if required:
                self.fail("the cloud served nothing; the leg under test did not run")
            return None, None
        return apply_changes(
            self.box_school.id, self.box_user, items, sync_origin="cloud-pull"
        ), items[0]

    def _push(self):
        """Box -> cloud. The box's delta, applied on the cloud."""
        rows, _meta = build_edge_delta_rows(self.box_school, entities=[ENTITY])
        items = [
            dict(r, id=self.cloud_row.pk)
            for r in _over_the_wire(rows)
            if str(r.get("id")) == str(self.box_row.pk)
        ]
        self.assertTrue(items, "the box sent nothing; the leg under test did not run")
        return apply_changes(
            self.cloud_school.id, self.cloud_user, items, sync_origin="edge-push"
        ), items[0]

    def _edit_on_the_box(self, name):
        """A local edit on a box whose clock runs six hours fast."""
        self.box_row.refresh_from_db()
        self.box_row.name = name
        self.box_row.save(update_fields=["name", "updated_at"])
        _force_stamp(
            self.model, self.box_row.pk, timezone.now() + dt.timedelta(hours=6)
        )
        self.box_row.refresh_from_db()

    def _edit_on_the_cloud(self, name):
        self.cloud_row.refresh_from_db()
        self.cloud_row.name = name
        self.cloud_row.save(update_fields=["name", "updated_at"])
        self.cloud_row.refresh_from_db()

    def _pending_conflicts(self):
        from apps.siteconfig.models import SyncConflict

        return SyncConflict.objects.filter(
            school=self.cloud_school,
            entity_type=ENTITY,
            entity_id=self.cloud_row.pk,
            status=SyncConflict.Status.PENDING,
        )

    # -- the run ----------------------------------------------------------- #
    def test_a_conflicted_row_applies_on_the_next_cycle_and_keeps_applying(self):
        from apps.sync_engine.conflict_actions import apply_resolution

        # (0) The two sides start in agreement. The box pulls; every field already
        #     matches, so this is the unchanged short circuit - and that is where the box
        #     learns which version of the cloud's row it is holding.
        out, _row = self._pull()
        self.assertEqual(out["results"][0]["status"], 200, out["results"])
        self.assertTrue(out["results"][0]["data"].get("unchanged"), out["results"])
        base_at_start = self.cloud_row.updated_at
        self.assertEqual(
            _ledger(self.box_school, self.box_row.pk).peer_updated_at, base_at_start
        )

        # (1) Concurrent edits. The box's clock is six hours fast.
        self._edit_on_the_box("Box edit")
        self._edit_on_the_cloud("Cloud edit")
        self.assertGreater(
            self.box_row.updated_at,
            self.cloud_row.updated_at,
            "the fast-box premise did not hold; this test would prove nothing",
        )

        # (2) The push must be REFUSED even though the box's clock wins.
        out, sent = self._push()
        self.assertEqual(
            sent.get("base_updated_at"),
            base_at_start.isoformat(),
            "the producer did not ship the base version it had recorded",
        )
        self.assertEqual(
            out["results"][0]["status"],
            409,
            "a concurrent cloud edit was silently overwritten by the faster clock",
        )
        self.cloud_row.refresh_from_db()
        self.assertEqual(self.cloud_row.name, "Cloud edit")
        conflict = self._pending_conflicts().first()
        self.assertIsNotNone(conflict, "no SyncConflict was opened for the refused row")

        # (3) A human settles it in the box's favour, through the real Sync Center path.
        #     Note what this does NOT do: touch the ledger. It is a bare save().
        ok, _detail = apply_resolution(conflict, "client", self.cloud_user)
        self.assertTrue(ok)
        self.cloud_row.refresh_from_db()
        self.assertEqual(self.cloud_row.name, "Box edit")
        self.assertIsNone(
            _ledger(self.cloud_school, self.cloud_row.pk),
            "resolution wrote a ledger row; this test's premise needs re-reading",
        )

        # (4) The next pull carries the resolved value down. Both sides already agree, so
        #     it is the unchanged short circuit again - which is precisely how the box's
        #     causality stamp catches up without anyone writing a row.
        out, _row = self._pull()
        self.assertEqual(out["results"][0]["status"], 200, out["results"])
        stamp = _ledger(self.box_school, self.box_row.pk).peer_updated_at
        self.assertEqual(stamp, self.cloud_row.updated_at)
        self.assertGreater(
            stamp, base_at_start, "the causality stamp never advanced past the conflict"
        )

        # (5) THE POINT. A fresh box edit, clock still six hours fast, now APPLIES.
        #     Feed the same decision the stamp the rejected design would have used and it
        #     still says conflict - which is the never-converging bug, in one assertion.
        self._edit_on_the_box("Box edit 2")
        self.assertEqual(
            _conflict_decision(
                ENTITY, "edge-push", self.box_row.updated_at,
                self.cloud_row.updated_at, base_updated_at=base_at_start,
            ),
            "conflict",
            "the pre-conflict base no longer re-conflicts; the negative control is dead",
        )
        out, sent = self._push()
        self.assertEqual(
            sent.get("base_updated_at"), self.cloud_row.updated_at.isoformat()
        )
        self.assertEqual(
            out["results"][0]["status"],
            200,
            "the resolved row conflicted again - this is the never-converging trap",
        )
        self.cloud_row.refresh_from_db()
        self.assertEqual(self.cloud_row.name, "Box edit 2")

        # (6) And it keeps applying. A rule that converges once and then jams is not
        #     convergence. From here the cloud has nothing to serve - the row it holds is
        #     exactly what sync wrote there, so it is correctly echo-suppressed - which
        #     means the box's recorded base now stays one version BEHIND the cloud's row
        #     for ever. That is the second mouth of the same trap, and these cycles are
        #     what caught it.
        for n in range(3, 7):
            served, _row = self._pull(required=False)
            self.assertIsNone(
                served,
                "the cloud re-served a row it had only just applied; that is an echo",
            )
            self._edit_on_the_box(f"Box edit {n}")
            out, _sent = self._push()
            self.assertEqual(
                out["results"][0]["status"],
                200,
                f"cycle {n} re-conflicted on a row with no concurrent cloud edit",
            )
            self.cloud_row.refresh_from_db()
            self.assertEqual(self.cloud_row.name, f"Box edit {n}")
        self.assertEqual(
            self._pending_conflicts().count(),
            0,
            "a converged row is still manufacturing conflicts",
        )

    def test_a_genuinely_concurrent_edit_still_conflicts_after_convergence(self):
        """Convergence must not have been bought by making the rail permissive again."""
        out, _row = self._pull()
        self.assertEqual(out["results"][0]["status"], 200, out["results"])

        self._edit_on_the_box("Box edit")
        self._edit_on_the_cloud("Cloud edit")
        out, _sent = self._push()
        self.assertEqual(out["results"][0]["status"], 409, out["results"])

        # Nobody resolved it. The cloud still holds its own divergent edit, so the very
        # next box edit - clock still six hours fast - must still be refused.
        self._edit_on_the_box("Box edit, again")
        out, _sent = self._push()
        self.assertEqual(
            out["results"][0]["status"],
            409,
            "a still-divergent row was applied once the machinery had converged once",
        )
        self.cloud_row.refresh_from_db()
        self.assertEqual(self.cloud_row.name, "Cloud edit")

    def test_the_echo_guard_does_not_swallow_a_local_edit_made_after_an_apply(self):
        """The guard fires ONLY while our row is untouched since our own sync apply.

        One local edit after the apply must put the row back under causal grading, or the
        guard would be a blanket "the peer always wins" and the audit's bug would be back.
        """
        out, _row = self._pull()
        self.assertEqual(out["results"][0]["status"], 200, out["results"])
        self._edit_on_the_box("Box edit")
        out, _sent = self._push()
        self.assertEqual(out["results"][0]["status"], 200, out["results"])

        # The cloud's row is now exactly what the push wrote. A HUMAN edits it there.
        self._edit_on_the_cloud("Cloud edit, made by a person")
        self._edit_on_the_box("Box edit 2")
        out, _sent = self._push()
        self.assertEqual(
            out["results"][0]["status"],
            409,
            "the echo guard let a genuinely concurrent cloud edit be overwritten",
        )
        self.cloud_row.refresh_from_db()
        self.assertEqual(self.cloud_row.name, "Cloud edit, made by a person")
