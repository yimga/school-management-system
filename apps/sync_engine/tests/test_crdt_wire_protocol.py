"""v4.00.13 — unit tests for apps/sync_engine/crdt_wire_protocol.py."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.sync_engine.crdt_wire_protocol import (
    GCounterOp,
    HLC,
    LWWOp,
    ORSetOp,
    gcounter_merge,
    gcounter_value,
    hlc_tick,
    lww_merge,
    orset_materialize,
    orset_merge,
    parse_wire_op,
)


class HLCTests(SimpleTestCase):
    def test_to_wire_round_trip(self):
        hlc = HLC(physical_ms=1000, logical=5, actor_id="alice")
        self.assertEqual(HLC.from_wire(hlc.to_wire()), hlc)

    def test_from_wire_rejects_bad_shape(self):
        with self.assertRaises(ValueError):
            HLC.from_wire("not-colon-separated")
        with self.assertRaises(ValueError):
            HLC.from_wire(None)  # type: ignore[arg-type]
        with self.assertRaises(ValueError):
            HLC.from_wire("abc:def:alice")  # non-int physical

    def test_ordering_by_physical_then_logical_then_actor(self):
        a = HLC(physical_ms=100, logical=0, actor_id="z")
        b = HLC(physical_ms=200, logical=0, actor_id="a")
        c = HLC(physical_ms=200, logical=1, actor_id="a")
        d = HLC(physical_ms=200, logical=1, actor_id="b")
        self.assertLess(a, b)
        self.assertLess(b, c)
        self.assertLess(c, d)

    def test_hlc_tick_physical_forward(self):
        prev = HLC(physical_ms=100, logical=5, actor_id="alice")
        nxt = hlc_tick(prev, now_ms=200, actor_id="alice")
        self.assertEqual(nxt.physical_ms, 200)
        self.assertEqual(nxt.logical, 0, "physical advance resets logical")

    def test_hlc_tick_physical_stalled(self):
        prev = HLC(physical_ms=200, logical=5, actor_id="alice")
        nxt = hlc_tick(prev, now_ms=100, actor_id="alice")
        self.assertEqual(nxt.physical_ms, 200, "physical stays at max")
        self.assertEqual(nxt.logical, 6, "logical increments when physical stalls")


class LWWMergeTests(SimpleTestCase):
    def _make(self, value, physical, logical=0, actor="a"):
        return LWWOp(kind="LWW", key="k", value=value,
                     hlc=HLC(physical_ms=physical, logical=logical, actor_id=actor))

    def test_none_identity(self):
        op = self._make("x", 100)
        self.assertEqual(lww_merge(op, None), op)
        self.assertEqual(lww_merge(None, op), op)
        self.assertIsNone(lww_merge(None, None))

    def test_larger_hlc_wins(self):
        a = self._make("old", 100)
        b = self._make("new", 200)
        self.assertEqual(lww_merge(a, b).value, "new")
        self.assertEqual(lww_merge(b, a).value, "new", "commutative")

    def test_key_mismatch_raises(self):
        a = LWWOp(kind="LWW", key="x", value=1, hlc=HLC(100, 0, "a"))
        b = LWWOp(kind="LWW", key="y", value=2, hlc=HLC(200, 0, "a"))
        with self.assertRaises(ValueError):
            lww_merge(a, b)

    def test_idempotent(self):
        op = self._make("x", 100)
        self.assertEqual(lww_merge(op, op).value, "x")


class ORSetTests(SimpleTestCase):
    def test_add_then_materialize(self):
        state = orset_merge({}, ORSetOp(kind="ORSET-ADD", set_key="s", element="x", tag="t1"))
        self.assertEqual(orset_materialize(state), frozenset({"x"}))

    def test_concurrent_add_remove_keeps_unobserved(self):
        # Add x with tag t1, then concurrent: another add with tag t2,
        # then remove observing only t1 — x stays because t2 is unobserved.
        state = {}
        state = orset_merge(state, ORSetOp(kind="ORSET-ADD", set_key="s", element="x", tag="t1"))
        state = orset_merge(state, ORSetOp(kind="ORSET-ADD", set_key="s", element="x", tag="t2"))
        state = orset_merge(state, ORSetOp(kind="ORSET-REMOVE", set_key="s", element="x", tag="", observed_tags=("t1",)))
        self.assertEqual(orset_materialize(state), frozenset({"x"}), "concurrent unobserved add survives remove")

    def test_remove_before_observed_add_stays_removed(self):
        remove = ORSetOp(
            kind="ORSET-REMOVE",
            set_key="s",
            element="x",
            tag="",
            observed_tags=("t1",),
        )
        add = ORSetOp(
            kind="ORSET-ADD",
            set_key="s",
            element="x",
            tag="t1",
        )
        remove_then_add = orset_merge(orset_merge({}, remove), add)
        add_then_remove = orset_merge(orset_merge({}, add), remove)
        self.assertEqual(orset_materialize(remove_then_add), frozenset())
        self.assertEqual(remove_then_add, add_then_remove)

    def test_full_remove_drops_element(self):
        state = {}
        state = orset_merge(state, ORSetOp(kind="ORSET-ADD", set_key="s", element="x", tag="t1"))
        state = orset_merge(state, ORSetOp(kind="ORSET-REMOVE", set_key="s", element="x", tag="", observed_tags=("t1",)))
        self.assertEqual(orset_materialize(state), frozenset())

    def test_unknown_kind_raises(self):
        with self.assertRaises(ValueError):
            orset_merge({}, ORSetOp(kind="ORSET-BOGUS", set_key="s", element="x", tag="t"))

    def test_input_state_not_mutated(self):
        original = {"x": {"t1"}}
        new_state = orset_merge(original, ORSetOp(kind="ORSET-ADD", set_key="s", element="x", tag="t2"))
        self.assertEqual(original, {"x": {"t1"}}, "merge must not mutate input")
        self.assertEqual(new_state["x"], {"t1", "t2"})


class GCounterTests(SimpleTestCase):
    def test_value_empty(self):
        self.assertEqual(gcounter_value({}), 0)

    def test_increment(self):
        state = gcounter_merge({}, GCounterOp(kind="GCOUNTER", counter_key="c", actor_id="a", value=5))
        self.assertEqual(gcounter_value(state), 5)

    def test_negative_value_rejected(self):
        with self.assertRaises(ValueError):
            gcounter_merge({}, GCounterOp(kind="GCOUNTER", counter_key="c", actor_id="a", value=-1))

    def test_two_actors_sum(self):
        state = {}
        state = gcounter_merge(state, GCounterOp(kind="GCOUNTER", counter_key="c", actor_id="a", value=3))
        state = gcounter_merge(state, GCounterOp(kind="GCOUNTER", counter_key="c", actor_id="b", value=4))
        self.assertEqual(gcounter_value(state), 7)

    def test_replay_is_idempotent_and_stale_cell_does_not_regress(self):
        op = GCounterOp(
            kind="GCOUNTER", counter_key="c", actor_id="a", value=5
        )
        state = gcounter_merge({}, op)
        state = gcounter_merge(state, op)
        state = gcounter_merge(
            state,
            GCounterOp(
                kind="GCOUNTER", counter_key="c", actor_id="a", value=3
            ),
        )
        self.assertEqual(state, {"a": 5})


class ParseWireOpTests(SimpleTestCase):
    def test_parse_lww(self):
        raw = {"kind": "LWW", "key": "k", "value": 42, "hlc": "100:0:alice"}
        op = parse_wire_op(raw)
        self.assertIsInstance(op, LWWOp)
        self.assertEqual(op.value, 42)

    def test_parse_orset_add(self):
        raw = {"kind": "ORSET-ADD", "set_key": "s", "element": "x", "tag": "t1"}
        op = parse_wire_op(raw)
        self.assertIsInstance(op, ORSetOp)
        self.assertEqual(op.kind, "ORSET-ADD")

    def test_parse_gcounter(self):
        raw = {"kind": "GCOUNTER", "counter_key": "c", "actor_id": "a", "value": 5}
        op = parse_wire_op(raw)
        self.assertIsInstance(op, GCounterOp)
        self.assertEqual(op.value, 5)

    def test_parse_rejects_non_idempotent_delta_only_counter(self):
        with self.assertRaisesMessage(ValueError, "absolute value"):
            parse_wire_op(
                {
                    "kind": "GCOUNTER",
                    "counter_key": "c",
                    "actor_id": "a",
                    "delta": 5,
                }
            )

    def test_parse_unknown_raises(self):
        with self.assertRaises(ValueError):
            parse_wire_op({"kind": "BOGUS"})

    def test_parse_non_dict_raises(self):
        with self.assertRaises(ValueError):
            parse_wire_op("not-a-dict")  # type: ignore[arg-type]
