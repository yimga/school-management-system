"""Postgres convergence proof for the LIVE CRDT rail (metric #25).

The green ``verify_crdt_convergence`` management command exercises in-memory
algebra on the LEGACY modules (``apps/sync_engine/crdt.py`` /
``crdt_wallet.py``). That proof never touches the code that actually runs in
production: ``apps/sync_engine/views_crdt.py::CRDTOpsApplyView`` + the wire
protocol in ``apps/sync_engine/crdt_wire_protocol.py``, which merge ops and
PERSIST the result to ``School.settings['crdt_state']`` inside a real
``transaction.atomic()`` guarded by ``select_for_update()``.

This module closes that gap. It drives the SAME set of ops in DIFFERENT orders
(and split across simulated devices / requests) THROUGH the live view's
persistence path against a real database, then asserts the persisted, durable
state is identical regardless of delivery order and that no concurrent edit is
lost. The convergence claim is therefore proven on the rail that ships, not on
a parallel in-memory toy.

Tagged ``@requires_postgres`` and wired into
``.github/workflows/django-tests-postgres.yml`` so the proof runs against the
production-class engine: only on Postgres does the view's ``select_for_update``
take a real row lock, so the test exercises the genuine
serialize-then-merge-then-persist path rather than a SQLite no-op.

Honest scope note: this proves *order-independent convergence on the live rail
through DB persistence* (the metric #25 deliverable). It does NOT attempt the
5-7 day full-application offline E2E, which remains a separate deferred item
(see ``apps/platform_runtime/tests/test_offline_multiday_replay_simulation``
for the adjacent multi-day replay simulation).
"""

from __future__ import annotations

import json
import unittest

from django.db import connection
from django.test import RequestFactory, TestCase, tag

from apps.accounts.models import User
from apps.schools.models import School

# The live rail under proof — NOT apps.sync_engine.crdt (the legacy in-memory
# module the management command checks). Importing the view + wire protocol is
# the structural guarantee that this test drives the code that actually runs.
from apps.sync_engine.crdt_wire_protocol import (
    gcounter_value,
    orset_materialize,
)
from apps.sync_engine.views_crdt import CRDTOpsApplyView

requires_postgres = unittest.skipUnless(
    connection.vendor == "postgresql",
    "Live CRDT convergence proof requires PostgreSQL: only there does the "
    "view's select_for_update take a real row lock (SQLite ignores it), so "
    "the serialize-merge-persist path is genuinely exercised.",
)


def _lww(key, value, physical, logical=0):
    """An approved LWW op on the low-risk ``student_note`` namespace."""
    return {
        "kind": "LWW",
        "entity": "student_note",
        "key": f"student_note:{key}",
        "value": value,
        # actor segment is overwritten by the view's bound actor; ordering for
        # convergence rides on (physical, logical) + the per-device actor.
        "hlc": f"{physical}:{logical}:wire",
    }


def _orset_add(element, tag):
    return {
        "kind": "ORSET-ADD",
        "entity": "lesson_plan_tags",
        "set_key": "lesson_plan_tags:plan-1",
        "element": element,
        "tag": tag,
        "observed_tags": [],
    }


def _orset_remove(element, observed_tags):
    return {
        "kind": "ORSET-REMOVE",
        "entity": "lesson_plan_tags",
        "set_key": "lesson_plan_tags:plan-1",
        "element": element,
        "tag": "",
        "observed_tags": list(observed_tags),
    }


def _gcounter(value):
    return {
        "kind": "GCOUNTER",
        "entity": "telemetry_counter",
        "counter_key": "telemetry_counter:offline-captures",
        "actor_id": "wire",  # overwritten by bound actor (= per-device cell)
        "value": value,
    }


@requires_postgres
@tag("tenants_rls")
class CRDTLiveRailConvergenceTests(TestCase):
    """Order-independent convergence proven on the persisted live rail."""

    def setUp(self):
        self.factory = RequestFactory()
        # Two distinct users/devices = two distinct bound actors. Distinct
        # actors matter: the view rebinds every op's actor to
        # ``u{user.pk}:{device_id}``, so for the G-Counter to *sum* (not max
        # over one cell) and for LWW ties to resolve deterministically, each
        # simulated device must be a separate actor.
        self.user_a = User.objects.create_user(username="crdt-dev-a", password="x")
        self.user_b = User.objects.create_user(username="crdt-dev-b", password="x")

    def _make_school(self, slug):
        return School.objects.create(name=slug, slug=slug, subdomain=slug)

    def _apply(self, school, user, ops, device_id):
        """Drive ONE op batch through the live view's persistence path."""
        request = self.factory.post(
            "/api/v1/crdt/apply/",
            data=json.dumps({"ops": ops, "device_id": device_id}),
            content_type="application/json",
        )
        request.user = user
        request.tenant = school
        response = CRDTOpsApplyView().post(request)
        self.assertEqual(response.status_code, 200, response.content)
        return json.loads(response.content)

    def _persisted_state(self, school):
        """Read the DURABLE crdt_state straight from the database row."""
        school.refresh_from_db()
        return school.settings.get("crdt_state") or {}

    def _materialize_from_persisted(self, school):
        """Materialize observable values from the persisted state.

        Reads the durable DB state (not the view's response body) and runs it
        back through the wire-protocol materializers — the same functions the
        live view uses — so we compare the converged, observable truth.
        """
        state = self._persisted_state(school)
        lww = {k: v.get("value") for k, v in (state.get("lww") or {}).items()}
        lww_hlc = {k: v.get("hlc") for k, v in (state.get("lww") or {}).items()}
        orset = {
            k: sorted(
                orset_materialize(
                    {el: set(tags) for el, tags in v.items()}
                )
            )
            for k, v in (state.get("orset") or {}).items()
        }
        gcounter = {
            k: gcounter_value(v) for k, v in (state.get("gcounter") or {}).items()
        }
        return {"lww": lww, "lww_hlc": lww_hlc, "orset": orset, "gcounter": gcounter}

    # ----- the op program: a fixed multi-device, multi-type edit set --------
    #
    # Three batches stand in for three devices that edited offline. The set is
    # the SAME across schools; only the *delivery order* of the batches (and,
    # in one test, the interleaving) changes. A correct CRDT must converge to
    # one state regardless.

    def _device_batches(self):
        # Device A: writes draft-1 early, draft-2 late; adds tags exam + quiz;
        #           bumps telemetry to 3.
        batch_a = [
            _lww("draft-1", "A-early", physical=100),
            _lww("draft-2", "A-late", physical=400),
            _orset_add("exam", "tag-A-exam"),
            _orset_add("quiz", "tag-A-quiz"),
            _gcounter(3),
        ]
        # Device B: overwrites draft-1 LATER (B must win on draft-1), writes
        #           draft-2 EARLIER (A must win on draft-2); removes the quiz
        #           tag it observed from A; bumps its own telemetry cell to 5.
        batch_b = [
            _lww("draft-1", "B-later", physical=300),
            _lww("draft-2", "B-early", physical=200),
            _orset_remove("quiz", ["tag-A-quiz"]),
            _gcounter(5),
        ]
        # Device C: re-adds quiz with a fresh tag the remove never observed (so
        #           quiz survives), writes draft-3; bumps its telemetry to 2.
        batch_c = [
            _orset_add("quiz", "tag-C-quiz"),
            _lww("draft-3", "C-only", physical=500),
            _gcounter(2),
        ]
        return batch_a, batch_b, batch_c

    def _drive_program(self, school, order):
        """Apply the 3 device batches in the given (school, user, device) order."""
        batch_a, batch_b, batch_c = self._device_batches()
        named = {
            "A": (self.user_a, "device-a", batch_a),
            "B": (self.user_b, "device-b", batch_b),
            "C": (self.user_a, "device-c", batch_c),
        }
        for letter in order:
            user, device_id, ops = named[letter]
            self._apply(school, user, ops, device_id)

    def _expected_converged(self):
        """The single state every delivery order must converge to."""
        return {
            "lww": {
                # draft-1: B (physical 300) beats A (physical 100)
                "student_note:draft-1": "B-later",
                # draft-2: A (physical 400) beats B (physical 200)
                "student_note:draft-2": "A-late",
                # draft-3: only C wrote it
                "student_note:draft-3": "C-only",
            },
            "orset": {
                # exam stays (added, never removed); quiz survives because C's
                # re-add tag was never observed by B's remove
                "lesson_plan_tags:plan-1": ["exam", "quiz"],
            },
            "gcounter": {
                # three distinct device cells sum: 3 + 5 + 2
                "telemetry_counter:offline-captures": 10,
            },
        }

    def _assert_matches_expected(self, school):
        mat = self._materialize_from_persisted(school)
        expected = self._expected_converged()
        self.assertEqual(mat["lww"], expected["lww"])
        self.assertEqual(mat["orset"], expected["orset"])
        self.assertEqual(mat["gcounter"], expected["gcounter"])

    # ----- the proofs -------------------------------------------------------

    def test_order_independent_convergence_on_persisted_rail(self):
        """Same ops, different delivery orders -> identical persisted state."""
        forward = self._make_school("crdt-conv-forward")
        reverse = self._make_school("crdt-conv-reverse")
        shuffled = self._make_school("crdt-conv-shuffled")

        self._drive_program(forward, ["A", "B", "C"])
        self._drive_program(reverse, ["C", "B", "A"])
        self._drive_program(shuffled, ["B", "C", "A"])

        forward_state = self._materialize_from_persisted(forward)
        reverse_state = self._materialize_from_persisted(reverse)
        shuffled_state = self._materialize_from_persisted(shuffled)

        # Convergence: every order yields byte-identical observable state,
        # INCLUDING the winning HLC stamps (not just the values) — so the LWW
        # winner is the same op, not a coincidentally-equal value.
        self.assertEqual(forward_state, reverse_state)
        self.assertEqual(forward_state, shuffled_state)

        # And it converges to the one correct answer, read from the DB.
        self._assert_matches_expected(forward)
        self._assert_matches_expected(reverse)
        self._assert_matches_expected(shuffled)

    def test_interleaved_per_op_delivery_converges(self):
        """Per-op interleaving across devices (not whole batches) also converges.

        This stresses the persist-read-merge-persist loop op by op: every
        single op is its own request that re-reads the durable state under
        ``select_for_update`` and writes it back, the worst case for ordering
        bugs. The end state must still equal the batch-delivered convergence.
        """
        batch_a, batch_b, batch_c = self._device_batches()
        # Round-robin the ops from the three devices into one interleaved stream
        # while preserving each device's own op order (causal within a device).
        streams = [
            [(self.user_a, "device-a", op) for op in batch_a],
            [(self.user_b, "device-b", op) for op in batch_b],
            [(self.user_a, "device-c", op) for op in batch_c],
        ]
        interleaved = []
        idx = 0
        while any(idx < len(s) for s in streams):
            for s in streams:
                if idx < len(s):
                    interleaved.append(s[idx])
            idx += 1

        school = self._make_school("crdt-conv-interleaved")
        for user, device_id, op in interleaved:
            self._apply(school, user, [op], device_id)

        self._assert_matches_expected(school)

    def test_idempotent_redelivery_does_not_lose_or_double(self):
        """Replaying the whole program twice is a no-op (at-least-once safe).

        Offline sync delivers at-least-once; the durable rail must be
        idempotent under full replay. After two passes the state must equal a
        single pass — no doubled counters, no resurrected/dropped tags.
        """
        once = self._make_school("crdt-conv-once")
        twice = self._make_school("crdt-conv-twice")

        self._drive_program(once, ["A", "B", "C"])

        self._drive_program(twice, ["A", "B", "C"])
        self._drive_program(twice, ["A", "B", "C"])  # full replay

        self.assertEqual(
            self._materialize_from_persisted(once),
            self._materialize_from_persisted(twice),
        )
        self._assert_matches_expected(twice)

    def test_concurrent_edit_to_same_key_keeps_higher_hlc_no_loss(self):
        """Two devices edit the SAME key concurrently; the rail keeps one, loses none.

        Both writes land durably through the live rail (no write is silently
        dropped before merge); the converged winner is the higher-HLC op, and
        it is the SAME winner regardless of which device's request arrived
        first — the definition of a conflict-free resolution on the live rail.
        """
        a_first = self._make_school("crdt-conv-afirst")
        b_first = self._make_school("crdt-conv-bfirst")

        # Same logical conflict on the same key, opposite request arrival order.
        a_op = _lww("clash", "from-A", physical=700)
        b_op = _lww("clash", "from-B", physical=900)  # higher HLC -> must win

        self._apply(a_first, self.user_a, [a_op], "device-a")
        self._apply(a_first, self.user_b, [b_op], "device-b")

        self._apply(b_first, self.user_b, [b_op], "device-b")
        self._apply(b_first, self.user_a, [a_op], "device-a")

        a_state = self._materialize_from_persisted(a_first)
        b_state = self._materialize_from_persisted(b_first)

        # Order-independent: identical converged state including the HLC stamp.
        self.assertEqual(a_state["lww"], b_state["lww"])
        self.assertEqual(a_state["lww_hlc"], b_state["lww_hlc"])
        # The higher-HLC write wins; the loser is not silently kept.
        self.assertEqual(a_state["lww"]["student_note:clash"], "from-B")
