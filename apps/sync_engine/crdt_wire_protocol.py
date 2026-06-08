"""CRDT offline-sync wire protocol — v4.00.12.

Closes the v3.99.13 deferral: "CRDT offline-sync vector mesh (Wave S-E ships
strategy table; wire protocol missing)".

This module defines the WIRE FORMAT for CRDT-style ops that travel between
offline clients and the platform. The strategy table lives in
``conflict_resolver.py``; this is the typed envelope + merge functions
that make multi-actor concurrent edits commutative + associative +
idempotent (the CRDT invariants).

Supported CRDT types in this protocol:

* ``LWW``  — Last-Write-Wins Register. Carries a Hybrid Logical Clock
             (HLC) so concurrent writes have a total order. The largest
             HLC wins on merge.
* ``ORSET``— Observed-Remove Set. Adds carry a unique tag; removes carry
             the tag-set of observed adds. Concurrent add-then-remove
             keeps the element only if the remove observed all adds.
* ``GCOUNTER`` — Grow-Only Counter with absolute per-actor cells. Merge =
             component-wise max, so retry is idempotent.

All ops are pure-Python — no DB writes — so they can be tested in
SimpleTestCase and run inside service workers / Tauri.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# ============================================================================
# Hybrid Logical Clock (HLC)
# ============================================================================


@dataclass(frozen=True, order=True)
class HLC:
    """Hybrid Logical Clock = (physical_ms, logical_counter, actor_id).

    Ordering is lexicographic: physical first, then logical, then actor.
    Actor breaks ties when physical AND logical match — guarantees a
    total order across actors without coordination.
    """

    physical_ms: int
    logical: int
    actor_id: str

    def to_wire(self) -> str:
        """Canonical wire format: ``<physical>:<logical>:<actor>``."""
        return f"{self.physical_ms}:{self.logical}:{self.actor_id}"

    @classmethod
    def from_wire(cls, raw: str) -> "HLC":
        if not isinstance(raw, str):
            raise ValueError(f"HLC wire format must be str, got {type(raw).__name__}")
        parts = raw.split(":", 2)
        if len(parts) != 3:
            raise ValueError(f"HLC wire format requires 3 colon-separated parts, got: {raw!r}")
        try:
            physical_ms = int(parts[0])
            logical = int(parts[1])
        except (ValueError, TypeError) as exc:
            raise ValueError(f"HLC parse failed for {raw!r}: {exc}") from exc
        actor_id = parts[2].strip()
        if physical_ms < 0 or logical < 0:
            raise ValueError("HLC physical_ms and logical must be non-negative")
        if not actor_id or len(actor_id) > 128:
            raise ValueError("HLC actor_id must be 1-128 characters")
        return cls(physical_ms=physical_ms, logical=logical, actor_id=actor_id)


def hlc_tick(prev: HLC, *, now_ms: int, actor_id: str) -> HLC:
    """Advance a Hybrid Logical Clock following the standard HLC update rule.

    If physical clock moved forward, take wall-clock + reset logical to 0.
    Otherwise increment logical and keep physical.
    """
    if now_ms > prev.physical_ms:
        return HLC(physical_ms=now_ms, logical=0, actor_id=actor_id)
    return HLC(physical_ms=prev.physical_ms, logical=prev.logical + 1, actor_id=actor_id)


# ============================================================================
# LWW Register
# ============================================================================


@dataclass(frozen=True)
class LWWOp:
    """Single Last-Write-Wins assignment."""

    kind: str  # "LWW"
    key: str
    value: Any
    hlc: HLC

    def to_wire(self) -> dict[str, Any]:
        return {"kind": "LWW", "key": self.key, "value": self.value, "hlc": self.hlc.to_wire()}


def lww_merge(a: LWWOp | None, b: LWWOp | None) -> LWWOp | None:
    """Commutative + associative + idempotent: pick the op with the larger HLC.

    None is the identity. Mixed-key inputs are an error (caller groups by key)."""
    if a is None:
        return b
    if b is None:
        return a
    if a.key != b.key:
        raise ValueError(f"lww_merge: key mismatch: {a.key!r} vs {b.key!r}")
    return a if a.hlc >= b.hlc else b


# ============================================================================
# Observed-Remove Set (OR-Set)
# ============================================================================


@dataclass(frozen=True)
class ORSetOp:
    """One add or remove on an Observed-Remove Set."""

    kind: str  # "ORSET-ADD" or "ORSET-REMOVE"
    set_key: str
    element: str
    tag: str           # uuid hex for add; ignored on remove
    observed_tags: tuple[str, ...] = ()  # tags this remove witnessed

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "set_key": self.set_key,
            "element": self.element,
            "tag": self.tag,
            "observed_tags": list(self.observed_tags),
        }


def orset_merge(
    state: dict[str, set[str]],
    op: ORSetOp,
) -> dict[str, set[str]]:
    """Merge one op into the running tag-set state. Returns a new dict.

    ``state[element]`` is the set of live (unremoved) tags. The element is
    "present" iff its tag set is non-empty after the merge.
    """
    new_state = {k: set(v) for k, v in state.items()}
    removed_key = f"__removed__:{op.element}"
    removed = new_state.setdefault(removed_key, set())
    bucket = new_state.setdefault(op.element, set())
    if op.kind == "ORSET-ADD":
        if not op.tag:
            raise ValueError("OR-Set add requires a non-empty tag")
        if op.tag not in removed:
            bucket.add(op.tag)
    elif op.kind == "ORSET-REMOVE":
        for observed in op.observed_tags:
            bucket.discard(observed)
            removed.add(observed)
        if not bucket:
            del new_state[op.element]
    else:
        raise ValueError(f"unknown OR-Set op kind: {op.kind!r}")
    if not bucket:
        new_state.pop(op.element, None)
    if not removed:
        new_state.pop(removed_key, None)
    return new_state


def orset_materialize(state: dict[str, set[str]]) -> frozenset[str]:
    """Return the set of currently-present elements from the tag-set state."""
    return frozenset(
        key
        for key, tags in state.items()
        if tags and not key.startswith("__removed__:")
    )


# ============================================================================
# Grow-only Counter (G-Counter)
# ============================================================================


@dataclass(frozen=True)
class GCounterOp:
    """Absolute value of one actor cell in a state-based G-Counter."""

    kind: str  # "GCOUNTER"
    counter_key: str
    actor_id: str
    value: int  # non-negative, monotonically increasing

    def to_wire(self) -> dict[str, Any]:
        return {
            "kind": "GCOUNTER",
            "counter_key": self.counter_key,
            "actor_id": self.actor_id,
            "value": int(self.value),
        }


def gcounter_merge(
    state: dict[str, int],
    op: GCounterOp,
) -> dict[str, int]:
    """Merge an absolute actor-cell value using component-wise max.

    Retrying the same operation is idempotent. Negative values are rejected
    because a G-Counter is grow-only; use a PN-Counter for decrements.
    """
    if op.value < 0:
        raise ValueError(f"GCounterOp value must be >= 0, got {op.value}")
    new_state = dict(state)
    new_state[op.actor_id] = max(new_state.get(op.actor_id, 0), op.value)
    return new_state


def gcounter_value(state: dict[str, int]) -> int:
    """Total value = sum of per-actor cells."""
    return sum(int(v) for v in state.values() if isinstance(v, int))


# ============================================================================
# Wire-level parse + dispatch
# ============================================================================


def parse_wire_op(raw: dict[str, Any]) -> LWWOp | ORSetOp | GCounterOp:
    """Parse a single op off the wire into its typed dataclass."""
    if not isinstance(raw, dict):
        raise ValueError("op must be a dict")
    kind = str(raw.get("kind") or "").strip().upper()
    if kind == "LWW":
        return LWWOp(
            kind="LWW",
            key=str(raw["key"]),
            value=raw["value"],
            hlc=HLC.from_wire(str(raw["hlc"])),
        )
    if kind in ("ORSET-ADD", "ORSET-REMOVE"):
        return ORSetOp(
            kind=kind,
            set_key=str(raw["set_key"]),
            element=str(raw["element"]),
            tag=str(raw.get("tag") or ""),
            observed_tags=tuple(raw.get("observed_tags") or ()),
        )
    if kind == "GCOUNTER":
        if "value" not in raw:
            raise ValueError(
                "GCOUNTER requires absolute value; delta-only operations are not replay-safe"
            )
        return GCounterOp(
            kind="GCOUNTER",
            counter_key=str(raw["counter_key"]),
            actor_id=str(raw["actor_id"]),
            value=int(raw["value"]),
        )
    raise ValueError(f"unknown CRDT op kind: {kind!r}")
