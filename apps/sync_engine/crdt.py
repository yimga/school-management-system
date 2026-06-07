"""Conflict-free replicated data types for offline-first convergence (Wave F).

REAL CRDTs — order-independent, idempotent, commutative, associative merges that
converge to the same state on every replica regardless of delivery order (mesh /
LAN / cloud). This is the deliberate opposite of the wall-clock "last-write-wins"
merger rejected from the original manifesto: conflict resolution here is by a
**Lamport logical clock** with a **replica-id tiebreak**, so it is deterministic
and causal, never a wall-clock race.

Primitives:
  * ``lamport_tick`` — advance a Lamport clock on receive.
  * ``LWWRegister`` — last-writer-wins single value, ordered by (lamport, replica).
  * ``GSet`` — grow-only set (union-merge), the basis for append-only op logs.

Pure data structures (no Django) so they run identically on an edge node and the
cloud. See docs/GLOCAL_SOVEREIGNTY_PLAN.md (Wave F) and ``crdt_wallet.py``.
"""

from __future__ import annotations

from typing import Any, Iterable


def lamport_tick(local_clock: int, received_clock: int = 0) -> int:
    """Return the next Lamport timestamp given local + (optional) received clocks."""
    return max(int(local_clock), int(received_clock)) + 1


class LWWRegister:
    """Last-writer-wins register. Convergence by (lamport, replica_id) ordering.

    Two replicas that have seen the same set of writes hold the same value,
    independent of the order in which those writes arrived.
    """

    __slots__ = ("value", "lamport", "replica_id")

    def __init__(self, value: Any = None, lamport: int = 0, replica_id: str = ""):
        self.value = value
        self.lamport = int(lamport)
        self.replica_id = str(replica_id)

    def _rank(self):
        return (self.lamport, self.replica_id)

    def set(self, value: Any, lamport: int, replica_id: str) -> "LWWRegister":
        candidate = LWWRegister(value, lamport, replica_id)
        return self.merge(candidate)

    def merge(self, other: "LWWRegister") -> "LWWRegister":
        """Idempotent, commutative, associative merge — keep the higher rank."""
        if other is None:
            return self
        if other._rank() > self._rank():
            self.value, self.lamport, self.replica_id = (
                other.value,
                other.lamport,
                other.replica_id,
            )
        return self

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "lamport": self.lamport, "replica_id": self.replica_id}

    @classmethod
    def from_dict(cls, data: dict) -> "LWWRegister":
        return cls(data.get("value"), data.get("lamport", 0), data.get("replica_id", ""))

    def __eq__(self, other):
        return isinstance(other, LWWRegister) and self.to_dict() == other.to_dict()

    def __repr__(self):
        return f"LWWRegister(value={self.value!r}, lamport={self.lamport}, replica={self.replica_id!r})"


class GSet:
    """Grow-only set. Merge = union. Idempotent + commutative + associative."""

    __slots__ = ("_items",)

    def __init__(self, items: Iterable = ()):
        self._items = set(items)

    def add(self, item) -> "GSet":
        self._items.add(item)
        return self

    def merge(self, other: "GSet") -> "GSet":
        if other is not None:
            self._items |= other._items
        return self

    def __contains__(self, item):
        return item in self._items

    def __len__(self):
        return len(self._items)

    def values(self) -> set:
        return set(self._items)

    def __eq__(self, other):
        return isinstance(other, GSet) and self._items == other._items

    def __repr__(self):
        return f"GSet({sorted(self._items)!r})"
