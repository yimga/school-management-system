"""CRDT offline wallet — multi-terminal debit convergence (Wave F).

This closes the multi-terminal offline wallet-debit problem deliberately deferred
from Wave C's POS checkout. A wallet's movements are a **grow-only set of unique
operations** (each debit/credit keyed by a globally-unique op_id). Merging two
terminals' logs is a set union by op_id — idempotent (a replayed op is counted
once), commutative and associative — so every terminal converges to the same
balance regardless of how ops propagate (mesh / LAN / cloud).

Honest about CAP: you CANNOT prevent an overdraft across partitioned terminals
without coordination (that's a theorem, not a missing feature). So this layer
*detects* an overdraft on reconciliation and surfaces the deficit for follow-up,
rather than pretending to prevent it. Single-terminal / online callers can still
ask ``reserve_debit`` to reject locally when the balance is known.

Decimal-safe throughout. Pure data (no Django) — identical on edge + cloud.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

_KINDS = ("credit", "debit")


def _dec(value) -> Decimal:
    return value if isinstance(value, Decimal) else Decimal(str(value))


def make_op(op_id: str, kind: str, amount, *, terminal: str = "", lamport: int = 0) -> dict[str, Any]:
    if kind not in _KINDS:
        raise ValueError(f"kind must be one of {_KINDS}")
    return {
        "op_id": str(op_id),
        "kind": kind,
        "amount": str(_dec(amount)),  # stored as canonical string (Decimal-safe, JSON-safe)
        "terminal": str(terminal),
        "lamport": int(lamport),
    }


def apply_op(oplog: dict[str, dict], op: dict) -> dict[str, dict]:
    """Add an op to the log keyed by op_id. Idempotent: re-applying is a no-op."""
    oplog.setdefault(op["op_id"], op)
    return oplog


def merge_oplogs(*logs: dict[str, dict]) -> dict[str, dict]:
    """Union of op logs by op_id (conflict-free). Returns a new merged log."""
    merged: dict[str, dict] = {}
    for log in logs:
        for op_id, op in (log or {}).items():
            merged.setdefault(op_id, op)
    return merged


def effective_balance(initial, oplog: dict[str, dict]) -> Decimal:
    balance = _dec(initial)
    for op in oplog.values():
        amount = _dec(op["amount"])
        balance = balance + amount if op["kind"] == "credit" else balance - amount
    return balance


def detect_overdraft(initial, oplog: dict[str, dict]) -> dict[str, Any]:
    balance = effective_balance(initial, oplog)
    overdrawn = balance < Decimal("0")
    return {
        "overdrawn": overdrawn,
        "balance": str(balance),
        "deficit": str(-balance) if overdrawn else "0",
    }


def reserve_debit(
    oplog: dict[str, dict],
    *,
    op_id: str,
    amount,
    terminal: str = "",
    lamport: int = 0,
    initial=None,
    allow_overdraft: bool = True,
) -> dict[str, Any]:
    """Record a debit op. If ``initial`` is known and ``allow_overdraft`` is False
    (online single-terminal mode), reject when it would overdraw. Offline mode
    (default) always records and relies on ``detect_overdraft`` at reconciliation.
    Idempotent per op_id.
    """
    if op_id in oplog:
        return {"ok": True, "dedup": True, "balance": str(effective_balance(initial or 0, oplog))}
    if initial is not None and not allow_overdraft:
        projected = effective_balance(initial, oplog) - _dec(amount)
        if projected < Decimal("0"):
            return {
                "ok": False,
                "insufficient": True,
                "balance": str(effective_balance(initial, oplog)),
                "required": str(_dec(amount)),
            }
    apply_op(oplog, make_op(op_id, "debit", amount, terminal=terminal, lamport=lamport))
    result = {"ok": True, "op_id": str(op_id)}
    if initial is not None:
        result["balance"] = str(effective_balance(initial, oplog))
    return result
