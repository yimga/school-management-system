"""Self-check that the offline CRDTs converge (Wave F).

Runs a deterministic convergence assertion: the same op set, merged in two
different orders, must yield identical state. Exit 0 if the CRDT laws hold.

    python manage.py verify_crdt_convergence

SCOPE — what this command does and does NOT prove (read before trusting it):

This command checks the merge ALGEBRA in two layers:

  1. The LEGACY in-memory modules ``apps/sync_engine/crdt.py`` (LWW register)
     and ``crdt_wallet.py`` (wallet op-log) — order-independence + idempotence.
  2. (this wave) The LIVE wire-protocol merge functions in
     ``apps/sync_engine/crdt_wire_protocol.py`` — ``lww_merge`` /
     ``orset_merge`` / ``gcounter_merge`` — the *same functions the live
     ``CRDTOpsApplyView`` calls. So the command now exercises the algebra of
     the rail that actually runs, not only the parallel legacy toy.

It deliberately does NOT touch the DURABLE persistence path: the view's
``select_for_update`` row-lock + ``transaction.atomic()`` write to
``School.settings['crdt_state']``. That requires a database and a tenant row,
which a fast no-DB self-check command must not assume. The order-independent
convergence proof THROUGH that persisted live rail lives in the Postgres test
``apps/sync_engine/tests/test_crdt_live_rail_convergence.py`` (wired into
``.github/workflows/django-tests-postgres.yml``). The honest division of
labour: this command proves the merge algebra (legacy + live wire protocol);
that test proves the live rail converges once the merges are persisted under a
real DB transaction.

Neither this command nor that test claims a multi-day full-application offline
E2E — that remains a separate deferred item.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.sync_engine.crdt import LWWRegister
from apps.sync_engine.crdt_wallet import apply_op, effective_balance, make_op
from apps.sync_engine.crdt_wire_protocol import (
    HLC,
    GCounterOp,
    LWWOp,
    ORSetOp,
    gcounter_merge,
    gcounter_value,
    lww_merge,
    orset_materialize,
    orset_merge,
)


class Command(BaseCommand):
    help = "Verify the offline CRDTs (legacy in-memory + LIVE wire protocol) converge."

    def handle(self, *args, **options):
        # LWW register: order-independent.
        writes = [("x", 1, "n1"), ("y", 3, "n2"), ("z", 2, "n3")]
        a, b = LWWRegister(), LWWRegister()
        for v, c, n in writes:
            a.set(v, c, n)
        for v, c, n in reversed(writes):
            b.set(v, c, n)
        if a.value != b.value:
            raise CommandError(f"LWW divergence: {a.value!r} != {b.value!r}")

        # Wallet op-log: order-independent + idempotent.
        ops = [make_op(f"op{i}", "debit", "1.00", terminal=f"t{i % 3}") for i in range(6)]
        l1, l2 = {}, {}
        for op in ops:
            apply_op(l1, op)
        for op in reversed(ops):
            apply_op(l2, op)
            apply_op(l2, op)  # replay -> idempotent
        if effective_balance(10, l1) != effective_balance(10, l2):
            raise CommandError("wallet op-log divergence")
        if effective_balance(10, l1) != Decimal("4.00"):
            raise CommandError("wallet balance unexpected")

        # LIVE wire protocol algebra (the merge functions CRDTOpsApplyView uses).
        # Same ops, different orders, must yield identical materialized state.
        self._verify_live_wire_protocol()

        self.stdout.write(
            self.style.SUCCESS(
                "CRDT convergence OK (legacy LWW + wallet op-log + LIVE wire protocol)."
            )
        )
        self.stdout.write(
            "Note: this command proves the MERGE ALGEBRA (legacy + live wire "
            "protocol). The order-independent convergence proof through the "
            "PERSISTED live rail (CRDTOpsApplyView -> School.settings"
            "['crdt_state'], real DB transaction) is the Postgres test "
            "apps.sync_engine.tests.test_crdt_live_rail_convergence. Multi-day "
            "full-app offline E2E remains a separate deferred item."
        )

    def _verify_live_wire_protocol(self):
        """Exercise the live ``crdt_wire_protocol`` merges in two orders.

        Mirrors what ``CRDTOpsApplyView`` does in-process (without the DB) so a
        no-DB command can still catch an algebra regression on the code that
        actually runs.
        """
        # ---- LWW: highest HLC wins regardless of merge order. ----
        lww_ops = [
            LWWOp(kind="LWW", key="k", value="early",
                  hlc=HLC(physical_ms=100, logical=0, actor_id="dev-a")),
            LWWOp(kind="LWW", key="k", value="late",
                  hlc=HLC(physical_ms=300, logical=0, actor_id="dev-b")),
            LWWOp(kind="LWW", key="k", value="mid",
                  hlc=HLC(physical_ms=200, logical=0, actor_id="dev-c")),
        ]
        fwd = None
        for op in lww_ops:
            fwd = lww_merge(fwd, op)
        rev = None
        for op in reversed(lww_ops):
            rev = lww_merge(rev, op)
        if fwd.value != rev.value or fwd.value != "late":
            raise CommandError(
                f"live LWW wire divergence: {fwd.value!r} != {rev.value!r}"
            )

        # ---- OR-Set: concurrent re-add (unobserved tag) survives a remove. ----
        orset_ops = [
            ORSetOp(kind="ORSET-ADD", set_key="s", element="quiz", tag="t-a"),
            ORSetOp(kind="ORSET-REMOVE", set_key="s", element="quiz",
                    tag="", observed_tags=("t-a",)),
            ORSetOp(kind="ORSET-ADD", set_key="s", element="quiz", tag="t-c"),
        ]
        s_fwd = {}
        for op in orset_ops:
            s_fwd = orset_merge(s_fwd, op)
        s_rev = {}
        for op in reversed(orset_ops):
            s_rev = orset_merge(s_rev, op)
        if orset_materialize(s_fwd) != orset_materialize(s_rev):
            raise CommandError("live OR-Set wire divergence (order-dependent)")
        if orset_materialize(s_fwd) != frozenset({"quiz"}):
            raise CommandError("live OR-Set wire unexpected (unobserved re-add lost)")

        # ---- G-Counter: per-actor cells sum; replay is idempotent. ----
        gc_ops = [
            GCounterOp(kind="GCOUNTER", counter_key="c", actor_id="dev-a", value=3),
            GCounterOp(kind="GCOUNTER", counter_key="c", actor_id="dev-b", value=5),
            GCounterOp(kind="GCOUNTER", counter_key="c", actor_id="dev-c", value=2),
        ]
        g_fwd = {}
        for op in gc_ops:
            g_fwd = gcounter_merge(g_fwd, op)
        g_rev = {}
        for op in reversed(gc_ops):
            g_rev = gcounter_merge(g_rev, op)
            g_rev = gcounter_merge(g_rev, op)  # replay -> idempotent
        if gcounter_value(g_fwd) != gcounter_value(g_rev):
            raise CommandError("live G-Counter wire divergence")
        if gcounter_value(g_fwd) != 10:
            raise CommandError("live G-Counter wire unexpected sum")
