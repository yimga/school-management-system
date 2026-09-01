"""Is the delta rail's conflict resolution CAUSAL, or a race between two clocks?

THE QUESTION. ``apps.api.sync_services._conflict_decision`` is the only thing standing
between a box's offline edit and the cloud's copy of the same row, and it decides by
comparing two wall-clock ``updated_at`` values taken on two different machines. A box in
a school with no time source is not merely inaccurate, it is SYSTEMATICALLY ahead - the
same fact ``clock_offset`` was written to measure - so "newest wins" is not a race the
two sides enter on equal terms. It is a rule that names the box the winner in advance,
including when the cloud holds an edit the box has never seen.

WHAT CAUSALITY WOULD MEAN, and what it does not require. It does not require a version
vector per entity, which would be a rewrite of the wire, the models and the apply path.
It requires one thing the rail does not carry today: the version of the SERVER's row that
the incoming edit was derived from. With it the question stops being "whose clock is
larger" and becomes "did this side move on independently of the edit I am being handed" -
which is the actual definition of a concurrent write, and has no clock in it.

WHAT THESE TESTS HOLD.

  (a) The rail's decision is a wall-clock comparison, and an exact TIE - two writes no
      clock can order - used to be handed to the box. It is now a conflict.
  (b) ``_conflict_decision`` honours a causality token (``base_updated_at``) when the row
      carries one, and then outranks the clock in BOTH directions: a concurrent edit is a
      conflict even when the box's clock is ahead, and a descendant edit applies even when
      the box's clock is behind.
  (c) Policy still outranks causality. A protected (money/grades/identity) row is not
      made overwritable by a well-formed token.
  (d) The findings this audit could NOT close are sealed as findings, not papered over:
      the delta wire carries no causality field of its own yet, ``clock_offset``'s
      measurement never reaches the decision, and ``conflict_resolver``'s causal branch
      is unreachable from its production caller.
  (e) G8 parity: the row COUNT the module header claims as the XOR fold's mitigation is
      real and compared on the ENTITY path - and was entirely absent from the BUCKET path,
      which is not a diagnostic but the thing that decides which rows a repair serves.
"""
from __future__ import annotations

import datetime as dt
import uuid
from pathlib import Path

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.api.sync_services import (
    _conflict_decision,
    _get_entity_config,
    apply_changes,
)
from apps.sync_engine import parity

_REPO = Path(__file__).resolve().parents[3]


def _school_and_user(prefix):
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


# --------------------------------------------------------------------------- #
# (a) what the rail actually compares
# --------------------------------------------------------------------------- #
class WhatTheDeltaRailComparesTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()
        self.older = self.now - dt.timedelta(minutes=10)
        self.newer = self.now + dt.timedelta(minutes=10)

    def test_a_provably_newer_row_applies(self):
        self.assertEqual(
            _conflict_decision("student", "edge-push", self.newer, self.now), "apply"
        )

    def test_a_provably_older_row_is_a_conflict(self):
        self.assertEqual(
            _conflict_decision("student", "edge-push", self.older, self.now), "conflict"
        )

    def test_a_tie_is_not_an_ordering(self):
        """Two writes stamped identically by two different clocks are CONCURRENT.

        Handing the tie to the incoming row is the box-favouring default in miniature:
        the one case where the clocks say nothing at all, decided for the box anyway.
        Nothing legitimate produces the tie - no registered entity ships ``updated_at``
        as a rail field, so the two stamps are independent ``auto_now`` values - and the
        unchanged-value short circuit in ``_apply_changes_inner`` runs BEFORE this, so
        reaching it means the values genuinely differ.
        """
        self.assertEqual(
            _conflict_decision("student", "edge-push", self.now, self.now), "conflict"
        )
        self.assertEqual(
            _conflict_decision("student", "cloud-pull", self.now, self.now), "conflict"
        )

    def test_a_row_with_no_server_row_to_beat_still_applies(self):
        self.assertEqual(
            _conflict_decision("student", "edge-push", self.now, None), "apply"
        )

    def test_an_unprovable_timestamp_is_still_a_conflict(self):
        self.assertEqual(
            _conflict_decision("student", "edge-push", None, self.now), "conflict"
        )
        self.assertEqual(_conflict_decision("student", "edge-push", None, None), "apply")


# --------------------------------------------------------------------------- #
# (b) + (c) causality, when the row carries it
# --------------------------------------------------------------------------- #
class CausalityOutranksTheClockTests(SimpleTestCase):
    """``base_updated_at`` = the server version this edit was derived from."""

    def setUp(self):
        self.t0 = timezone.now() - dt.timedelta(hours=2)
        self.t1 = timezone.now() - dt.timedelta(hours=1)
        self.way_ahead = timezone.now() + dt.timedelta(hours=6)
        self.way_behind = timezone.now() - dt.timedelta(hours=6)

    def test_a_concurrent_edit_is_a_conflict_even_when_the_box_clock_runs_ahead(self):
        """The failure the whole audit is about, in one assertion.

        The box edited a row it last saw at ``t0``. The cloud has since moved that row on
        to ``t1`` independently. The box's clock is hours fast, so wall-clock LWW hands
        it the win and the cloud's edit is destroyed silently. With the base version
        present, the two edits are visibly concurrent and the row goes to Sync Center.
        """
        self.assertEqual(
            _conflict_decision(
                "student",
                "edge-push",
                self.way_ahead,
                self.t1,
                base_updated_at=self.t0,
            ),
            "conflict",
        )

    def test_a_descendant_edit_applies_even_when_the_box_clock_runs_behind(self):
        """The mirror image, which matters just as much on a SLOW box.

        The server has not moved since the version this edit was derived from, so the
        edit descends from what the server holds and there is nothing to adjudicate.
        Today a slow box loses that write to a clock comparison it cannot win.
        """
        self.assertEqual(
            _conflict_decision(
                "student",
                "edge-push",
                self.way_behind,
                self.t1,
                base_updated_at=self.t1,
            ),
            "apply",
        )

    def test_policy_still_outranks_causality(self):
        """A well-formed token must not become a way past a protected policy."""
        self.assertEqual(
            _conflict_decision(
                "fee_payment",
                "edge-push",
                self.way_ahead,
                self.t1,
                base_updated_at=self.t1,
            ),
            "conflict",
        )
        self.assertEqual(
            _conflict_decision(
                "fee_payment",
                "cloud-pull",
                self.way_behind,
                self.t1,
                base_updated_at=self.t0,
            ),
            "apply",
        )

    def test_no_token_leaves_every_existing_rule_exactly_as_it_was(self):
        self.assertEqual(
            _conflict_decision("student", "edge-push", self.way_ahead, self.t1), "apply"
        )
        self.assertEqual(
            _conflict_decision("student", "edge-push", self.way_behind, self.t1),
            "conflict",
        )

    def test_a_token_with_no_server_row_beside_it_changes_nothing(self):
        self.assertEqual(
            _conflict_decision(
                "student", "edge-push", self.way_ahead, None, base_updated_at=self.t0
            ),
            "apply",
        )


class TheTokenReachesTheDecisionThroughApplyChangesTests(TestCase):
    """A detector nothing calls is not a detector. This drives the real apply path."""

    def setUp(self):
        self.school, self.user, uid = _school_and_user("caus")
        model, _allowed = _get_entity_config(include_derived=True)["academic_year"]
        self.row = model.objects.create(
            school=self.school,
            name=f"Year {uid}",
            start_date="2026-09-01",
            end_date="2027-07-31",
        )

    def _push(self, **extra):
        item = {
            "entity_type": "academic_year",
            "id": self.row.pk,
            "updated_at": (timezone.now() + dt.timedelta(hours=6)).isoformat(),
            "changes": {"name": "Renamed by the box"},
        }
        item.update(extra)
        return apply_changes(
            self.school.id,
            self.user,
            [item],
            persist_conflicts=True,
            sync_origin="edge-push",
        )

    def test_without_a_token_the_faster_clock_still_wins(self):
        out = self._push()
        self.assertEqual(out["results"][0]["status"], 200, out["results"])

    def test_with_a_stale_base_version_the_row_becomes_a_conflict(self):
        base = self.row.updated_at - dt.timedelta(hours=1)
        out = self._push(base_updated_at=base.isoformat())
        self.assertEqual(
            out["results"][0]["status"],
            409,
            "the causality token never reached _conflict_decision",
        )
        self.assertTrue(
            out["conflicts"], "no SyncConflict was raised for a concurrent edit"
        )
        self.row.refresh_from_db()
        self.assertNotEqual(self.row.name, "Renamed by the box")

    def test_with_a_current_base_version_it_applies(self):
        out = self._push(base_updated_at=self.row.updated_at.isoformat())
        self.assertEqual(out["results"][0]["status"], 200, out["results"])


# --------------------------------------------------------------------------- #
# (d) the findings this audit could not close, sealed as findings
# --------------------------------------------------------------------------- #
class TheGapsThisAuditCouldNotCloseTests(SimpleTestCase):
    """Each of these is a STATEMENT OF FACT about the shipped system.

    They are written to fail if the fact changes, so the next person is forced to
    re-read the finding rather than inherit a stale one.
    """

    def test_the_delta_wire_still_carries_no_causality_field_of_its_own(self):
        """The producer does not yet stamp a base version onto a row.

        ``_conflict_decision`` honours one; ``edge_outbox`` does not emit one, because
        neither side stores the PEER's version of a row (``SyncApplyLedger`` records the
        LOCAL ``updated_at`` after an apply, for echo suppression). Closing this needs a
        column and a wire field, which is the remaining half of the work.
        """
        source = (
            (_REPO / "apps" / "sync_engine" / "edge_outbox.py")
            .read_text(encoding="utf-8")
            .lower()
        )
        for token in ("lamport", "hlc", "version_vector", "base_updated_at"):
            self.assertNotIn(
                token, source, f"edge_outbox now emits {token!r}; re-read the finding"
            )

    def test_clock_offset_is_measured_but_never_consumed_by_the_decision(self):
        """G7 measures the skew, records it, warns about it - and nothing reads it back.

        It also cannot: ``observe`` runs in ``sync_runner`` on the BOX, from the pull
        response's ``Date`` header, while an ``edge-push`` is graded on the CLOUD. The
        measurement is on the wrong side of the wire from the decision it would inform.
        """
        for module in (
            "apps/api/sync_services.py",
            "apps/sync_engine/conflict_resolver.py",
        ):
            source = (_REPO / module).read_text(encoding="utf-8")
            self.assertNotIn(
                "clock_offset.",
                source,
                f"{module} now calls clock_offset; the G7 finding must be revisited",
            )
        runner = (_REPO / "apps" / "sync_engine" / "sync_runner.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("clock_offset.observe", runner)

    def test_the_causal_resolver_is_unreachable_from_its_production_caller(self):
        """``conflict_resolver._causal_decision`` wants HLCs. Its caller sends datetimes.

        ``conflict_actions._policy_payload`` puts ``client_updated_at.isoformat()`` into
        ``remote_clock``. An aware ISO timestamp has FOUR colon-separated parts, so
        ``HLC.from_wire`` rejects it and every CAUSAL_LWW resolution degrades to
        ``manual_review`` - after which ``_decision_to_status`` settles it by comparing
        the same two wall clocks. Made to accept a timestamp, it would be wall-clock LWW
        wearing a causal name, which is worse than the honest refusal; so the refusal is
        sealed here instead of being "fixed".
        """
        from apps.sync_engine.conflict_resolver import _parse_causal_rank, resolve_one

        now = timezone.now()
        self.assertIsNone(_parse_causal_rank(now.isoformat()))
        decision = resolve_one(
            {
                "entity": "attendance_record",
                "remote_clock": now.isoformat(),
                "server_clock": (now - dt.timedelta(minutes=5)).isoformat(),
            }
        )
        self.assertEqual(decision["strategy"], "causal_lww")
        self.assertEqual(decision["action"], "manual_review")
        self.assertIn("requires remote_clock and server_clock", decision["reason"])

    def test_a_real_logical_clock_still_resolves_causally(self):
        from apps.sync_engine.conflict_resolver import resolve_one

        decision = resolve_one(
            {
                "entity": "attendance_record",
                "remote_clock": "2000:1:box",
                "server_clock": "1000:0:cloud",
            }
        )
        self.assertEqual(decision["action"], "keep_remote")


# --------------------------------------------------------------------------- #
# (e) G8 parity: is the count really the XOR fold's mitigation?
# --------------------------------------------------------------------------- #
class TheEntityCountIsTransmittedAndComparedTests(SimpleTestCase):
    """The header's claim, verified rather than trusted - on the ENTITY path."""

    def test_the_count_survives_the_wire(self):
        wire = parity.encode_digests({"student": {"n": 412, "h": "9f3a" * 4}})
        self.assertIn(":412:", wire)
        self.assertEqual(parity.decode_digests(wire)["student"]["n"], 412)

    def test_a_matching_digest_with_a_different_count_is_drift(self):
        """The assertion that makes the count a MITIGATION and not a decoration."""
        same = "9f3a" * 4
        out = parity.compare_digests(
            {"student": {"n": 2, "h": same}}, {"student": {"n": 3, "h": same}}
        )
        self.assertEqual(out["drifted"], ["student"])
        self.assertEqual(out["detail"]["student"]["kind"], "row_count")
        self.assertFalse(out["in_parity"])

    def test_a_matching_count_with_a_different_digest_is_also_drift(self):
        out = parity.compare_digests(
            {"student": {"n": 2, "h": "a" * 16}}, {"student": {"n": 2, "h": "b" * 16}}
        )
        self.assertEqual(out["drifted"], ["student"])
        self.assertEqual(out["detail"]["student"]["kind"], "row_values")

    def test_what_the_count_still_cannot_catch_is_stated_honestly(self):
        """An EVEN cancellation on each side defeats digest AND count together.

        Two rows sharing an identity and their rail values fold to zero. A side holding
        one such pair and a side holding a DIFFERENT such pair therefore agree on both
        numbers while holding no data in common. The count catches odd duplication and
        every row-count difference; it does not catch this, and the module header no
        longer claims it does. The remaining defence is that an identity cannot be
        duplicated by this module's own spelling - see the namespacing tests below.
        """
        a = parity._row_digest("shared-anchor", {"name": "A"})
        b = parity._row_digest("shared-anchor", {"name": "A"})
        left = bytes(x ^ y for x, y in zip(a, b))
        c = parity._row_digest("other-anchor", {"name": "Z"})
        d = parity._row_digest("other-anchor", {"name": "Z"})
        right = bytes(x ^ y for x, y in zip(c, d))
        self.assertEqual(left, right)
        self.assertTrue(
            parity.compare_digests(
                {"student": {"n": 2, "h": left.hex()}},
                {"student": {"n": 2, "h": right.hex()}},
            )["in_parity"]
        )


class TheBucketPathMustCarryTheCountTooTests(SimpleTestCase):
    """The bucket path is not a diagnostic. It decides which rows a repair SERVES.

    ``sync_bundle_api`` narrows a repair pull to ``drifting_buckets(...)``, and
    ``edge_outbox`` filters the bundle to exactly those buckets. A bucket comparison with
    no count is therefore a localiser that can contradict the detector: the entity digest
    reports drift on a row-count difference, the bucket comparison sees matching folds,
    and the cloud serves nothing while the runner reports a repair.
    """

    def test_bucket_digests_report_a_count_per_bucket(self):
        d = {"buckets": 8, "b": {1: "a" * 16}, "c": {1: 3}}
        self.assertEqual(parity.decode_buckets(parity.encode_buckets(d)), d)

    def test_counts_that_disagree_are_drift_even_when_the_folds_agree(self):
        a = {"buckets": 8, "b": {1: "a" * 16}, "c": {1: 3}}
        b = {"buckets": 8, "b": {1: "a" * 16}, "c": {1: 1}}
        self.assertEqual(parity.drifting_buckets(a, b), [1])

    def test_counts_that_agree_are_not_drift(self):
        a = {"buckets": 8, "b": {1: "a" * 16}, "c": {1: 3}}
        self.assertEqual(parity.drifting_buckets(a, dict(a)), [])

    def test_an_older_peer_that_sends_no_counts_is_still_comparable(self):
        """A cloud that predates the count must not read as total drift, and must not
        read as agreement either: it falls back to exactly the old comparison."""
        new = {"buckets": 8, "b": {1: "a" * 16, 2: "b" * 16}, "c": {1: 3, 2: 1}}
        old = {"buckets": 8, "b": {1: "a" * 16, 2: "c" * 16}}
        self.assertEqual(parity.drifting_buckets(new, old), [2])
        self.assertEqual(parity.drifting_buckets(old, new), [2])

    def test_the_old_16_character_rule_still_reads_a_new_segment(self):
        """The count rides as a THIRD field, after a full-width digest, so a peer running
        the old ``digest[:16]`` decoder truncates it away and reads the right digest."""
        wire = parity.encode_buckets({"buckets": 8, "b": {1: "a" * 16}, "c": {1: 3}})
        self.assertEqual(wire, "8|1:" + "a" * 16 + ":3")
        segment = wire.partition("|")[2]
        _idx, _, rest = segment.partition(":")
        self.assertEqual(rest[:16], "a" * 16)

    def test_a_short_digest_never_gets_a_count_appended(self):
        """Only a full-width digest can carry one without confusing an old decoder."""
        self.assertEqual(
            parity.encode_buckets({"buckets": 8, "b": {1: "aaaa"}, "c": {1: 3}}),
            "8|1:aaaa",
        )

    def test_the_old_wire_still_round_trips_unchanged(self):
        d = {"buckets": 64, "b": {0: "aaaa", 7: "bbbb"}}
        self.assertEqual(parity.decode_buckets(parity.encode_buckets(d)), d)


class TheIdentityNamespaceMustBeInjectiveTests(SimpleTestCase):
    """``client_offline_id`` has no unique constraint and no format rule.

    Nothing stopped an anchor spelled ``"pk:7"`` from digesting under the same identity
    as the unanchored row with pk 7 - and two rows with one identity and equal values
    CANCEL in the XOR fold, which is the one failure the count cannot see.
    """

    def test_an_anchor_that_looks_like_a_pk_does_not_collide_with_that_pk(self):
        anchored = parity._identity_of(
            {"client_offline_id": "pk:7", "id": 99}, "client_offline_id", "id"
        )
        by_pk = parity._identity_of(
            {"client_offline_id": "", "id": 7}, "client_offline_id", "id"
        )
        self.assertNotEqual(anchored, by_pk)

    def test_the_bundle_spelling_agrees_with_the_digest_spelling(self):
        """If the two disagree the repair serves the wrong buckets and reports success."""
        for row in (
            {"client_offline_id": "pk:7", "id": 99},
            {"client_offline_id": "", "id": 7},
            {"client_offline_id": "  ", "id": 8},
            {"client_offline_id": "3f2b-offline", "id": 9},
        ):
            self.assertEqual(
                parity.bundle_row_identity(row),
                parity._identity_of(row, "client_offline_id", "id"),
                row,
            )

    def test_an_ordinary_anchor_is_spelled_exactly_as_before(self):
        """Renaming every anchored identity would change every anchored row's digest and
        make a fleet mid-upgrade report total drift on links schools pay for by the
        megabyte. Only the colliding shape moves."""
        self.assertEqual(
            parity._identity_of(
                {"client_offline_id": "3f2b-offline", "id": 9}, "client_offline_id", "id"
            ),
            "3f2b-offline",
        )
        self.assertEqual(
            parity._identity_of(
                {"client_offline_id": "", "id": 9}, "client_offline_id", "id"
            ),
            "pk:9",
        )


class TheDigestsAgreeWithEachOtherOnRealRowsTests(TestCase):
    def setUp(self):
        self.school, self.user, uid = _school_and_user("par")
        self.model, self.allowed = _get_entity_config(include_derived=True)[
            "academic_year"
        ]
        self.rows = [
            self.model.objects.create(
                school=self.school,
                name=f"Year {i} {uid}",
                start_date="2026-09-01",
                end_date="2027-07-31",
            )
            for i in range(9)
        ]

    def test_the_bucket_counts_add_up_to_the_entity_count(self):
        """The localiser and the detector must be counting the same rows."""
        whole = parity.entity_digest(
            self.school, "academic_year", self.model, self.allowed
        )
        buckets = parity.bucket_digests(
            self.school, "academic_year", self.model, self.allowed, buckets=8
        )
        self.assertEqual(whole["n"], 9)
        self.assertEqual(sum((buckets.get("c") or {}).values()), whole["n"])

    def test_two_rows_that_would_have_shared_an_identity_no_longer_cancel(self):
        """Plant the collision the old spelling allowed and prove the fold survives it."""
        if "client_offline_id" not in parity._concrete_names(self.model):
            self.skipTest("academic_year has no client_offline_id anchor to collide with")
        victim = self.rows[0]
        twin = self.model.objects.create(
            school=self.school,
            name=victim.name,
            start_date=victim.start_date,
            end_date=victim.end_date,
            client_offline_id=f"pk:{victim.pk}",
        )
        self.addCleanup(twin.delete)
        fields = parity._hashable_field_names(self.model, self.allowed)
        digests = {
            parity._row_digest(
                parity._identity_of(
                    {
                        "client_offline_id": getattr(row, "client_offline_id", ""),
                        "id": row.pk,
                    },
                    "client_offline_id",
                    "id",
                ),
                {f: getattr(row, f, None) for f in fields},
            )
            for row in (victim, twin)
        }
        self.assertEqual(
            len(digests), 2, "the two rows still digest identically and cancel"
        )
