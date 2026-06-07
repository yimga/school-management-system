"""Self-check that the offline CRDTs converge (Wave F).

Runs a deterministic convergence assertion: the same op set, merged in two
different orders, must yield identical state. Exit 0 if the CRDT laws hold.

    python manage.py verify_crdt_convergence
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.sync_engine.crdt import LWWRegister
from apps.sync_engine.crdt_wallet import apply_op, effective_balance, make_op


class Command(BaseCommand):
    help = "Verify the offline CRDTs (LWW register + wallet op-log) converge."

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

        self.stdout.write(self.style.SUCCESS("CRDT convergence OK (LWW + wallet op-log)"))
