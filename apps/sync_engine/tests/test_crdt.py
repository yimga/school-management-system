"""Wave F — CRDT convergence + offline wallet.

Proves the merges are order-independent, idempotent and commutative (true CRDT
laws), and that multi-terminal offline wallet debits converge with honest
overdraft detection.
"""

from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase

from apps.sync_engine.crdt import GSet, LWWRegister, lamport_tick
from apps.sync_engine.crdt_wallet import (
    apply_op,
    detect_overdraft,
    effective_balance,
    make_op,
    merge_oplogs,
    reserve_debit,
)


class LamportTests(SimpleTestCase):
    def test_tick_advances_past_max(self):
        self.assertEqual(lamport_tick(3, 5), 6)
        self.assertEqual(lamport_tick(5, 3), 6)
        self.assertEqual(lamport_tick(0), 1)


class LWWRegisterTests(SimpleTestCase):
    def test_higher_lamport_wins(self):
        r = LWWRegister("a", 1, "n1")
        r.set("b", 2, "n2")
        self.assertEqual(r.value, "b")

    def test_replica_id_tiebreak(self):
        r = LWWRegister("a", 5, "n1")
        r.set("b", 5, "n2")  # same lamport -> higher replica_id wins
        self.assertEqual(r.value, "b")

    def test_merge_is_order_independent(self):
        # two replicas see the same 3 writes in different orders -> same value
        writes = [("x", 1, "n1"), ("y", 3, "n2"), ("z", 2, "n3")]
        r1 = LWWRegister()
        for v, c, n in writes:
            r1.set(v, c, n)
        r2 = LWWRegister()
        for v, c, n in reversed(writes):
            r2.set(v, c, n)
        self.assertEqual(r1.value, r2.value)
        self.assertEqual(r1.value, "y")  # highest lamport

    def test_merge_idempotent(self):
        r = LWWRegister("a", 2, "n1")
        snapshot = r.to_dict()
        r.merge(LWWRegister.from_dict(snapshot))
        self.assertEqual(r.to_dict(), snapshot)


class GSetTests(SimpleTestCase):
    def test_union_commutative_idempotent(self):
        a = GSet({1, 2})
        b = GSet({2, 3})
        ab = GSet(a.values()).merge(b)
        ba = GSet(b.values()).merge(a)
        self.assertEqual(ab, ba)
        self.assertEqual(ab.values(), {1, 2, 3})
        ab.merge(b)  # idempotent
        self.assertEqual(ab.values(), {1, 2, 3})


class CrdtWalletTests(SimpleTestCase):
    def test_apply_op_idempotent(self):
        log: dict = {}
        op = make_op("op1", "debit", "5.00", terminal="t1")
        apply_op(log, op)
        apply_op(log, op)  # same op_id again
        self.assertEqual(len(log), 1)

    def test_effective_balance_decimal(self):
        log: dict = {}
        apply_op(log, make_op("c1", "credit", "10.00"))
        apply_op(log, make_op("d1", "debit", "3.50"))
        self.assertEqual(effective_balance(0, log), Decimal("6.50"))

    def test_merge_is_commutative(self):
        a = {}
        apply_op(a, make_op("d1", "debit", "6.00", terminal="A"))
        b = {}
        apply_op(b, make_op("d2", "debit", "7.00", terminal="B"))
        ab = merge_oplogs(a, b)
        ba = merge_oplogs(b, a)
        self.assertEqual(effective_balance(10, ab), effective_balance(10, ba))

    def test_multi_terminal_offline_overdraft_detected(self):
        # initial 10; terminal A debits 6 offline, terminal B debits 7 offline
        a = {}
        reserve_debit(a, op_id="A-1", amount="6.00", terminal="A")  # offline: records
        b = {}
        reserve_debit(b, op_id="B-1", amount="7.00", terminal="B")  # offline: records
        merged = merge_oplogs(a, b)
        status = detect_overdraft(10, merged)
        self.assertTrue(status["overdrawn"])
        self.assertEqual(status["balance"], "-3.00")
        self.assertEqual(status["deficit"], "3.00")

    def test_convergence_same_balance_regardless_of_merge_order(self):
        ops = [make_op(f"op{i}", "debit", "1.00", terminal=f"t{i%3}") for i in range(6)]
        r1: dict = {}
        for op in ops:
            apply_op(r1, op)
        r2: dict = {}
        for op in reversed(ops):
            apply_op(r2, op)
        self.assertEqual(effective_balance(10, r1), effective_balance(10, r2))
        self.assertEqual(effective_balance(10, r1), Decimal("4.00"))

    def test_online_mode_rejects_overdraft(self):
        log: dict = {}
        # online single-terminal: known balance, refuse overdraft
        res = reserve_debit(log, op_id="x", amount="20.00", initial=10, allow_overdraft=False)
        self.assertFalse(res["ok"])
        self.assertTrue(res["insufficient"])
        self.assertEqual(len(log), 0)  # nothing recorded

    def test_reserve_debit_idempotent(self):
        log: dict = {}
        reserve_debit(log, op_id="x", amount="5.00", initial=10)
        reserve_debit(log, op_id="x", amount="5.00", initial=10)  # same op
        self.assertEqual(effective_balance(10, log), Decimal("5.00"))
