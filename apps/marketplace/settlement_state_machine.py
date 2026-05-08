"""Settlement state machine — legal transition validator.

Composes with ``apps.marketplace.settlement_truth`` (canonical phase labels) to
enforce that ledger entries can only move along documented edges. Calling code
should request a transition via :func:`assert_legal_transition` (raises) or
:func:`is_legal_transition` (boolean) and only then write the new ledger event.

The transitions intentionally stay small — every edge maps to a real provider
event we already see in the wild (Stripe / Paystack / Flutterwave / aggregator).
"""

from __future__ import annotations

from .settlement_truth import (
    PHASE_OTHER,
    PHASE_SETTLEMENT_EXTERNAL_BLOCKED,
    PHASE_SETTLEMENT_FAILED,
    PHASE_SETTLEMENT_PAID,
    PHASE_SETTLEMENT_PENDING,
    PHASE_SETTLEMENT_READY,
    PHASE_SETTLEMENT_RECONCILED,
)


# Legal transitions — the directed graph.
# {from_phase: {to_phase, ...}}
_LEGAL_EDGES: dict[str, frozenset[str]] = {
    PHASE_OTHER: frozenset({PHASE_SETTLEMENT_PENDING, PHASE_SETTLEMENT_EXTERNAL_BLOCKED}),
    PHASE_SETTLEMENT_PENDING: frozenset(
        {
            PHASE_SETTLEMENT_READY,
            PHASE_SETTLEMENT_EXTERNAL_BLOCKED,
            PHASE_SETTLEMENT_FAILED,
            PHASE_SETTLEMENT_PAID,  # provider may go straight pending->paid
        }
    ),
    PHASE_SETTLEMENT_EXTERNAL_BLOCKED: frozenset(
        {PHASE_SETTLEMENT_PENDING, PHASE_SETTLEMENT_READY, PHASE_SETTLEMENT_FAILED}
    ),
    PHASE_SETTLEMENT_READY: frozenset({PHASE_SETTLEMENT_PAID, PHASE_SETTLEMENT_FAILED}),
    PHASE_SETTLEMENT_PAID: frozenset({PHASE_SETTLEMENT_RECONCILED, PHASE_SETTLEMENT_FAILED}),
    # FAILED is intentionally a sink unless an operator opens a new attempt
    # (which writes a new pending row rather than reusing the failed one).
    PHASE_SETTLEMENT_FAILED: frozenset(),
    PHASE_SETTLEMENT_RECONCILED: frozenset(),
}


class IllegalSettlementTransition(ValueError):
    """Raised when a transition is not in the legal-edges graph."""


def is_legal_transition(from_phase: str, to_phase: str) -> bool:
    """Pure check — does the edge exist?

    Unknown ``from_phase`` values are normalised to :data:`PHASE_OTHER` so a
    fresh ledger entry can always start at pending or external_blocked.
    """
    if from_phase == to_phase:
        # Self-transitions are always allowed (for re-emit / idempotency).
        return True
    key = from_phase if from_phase in _LEGAL_EDGES else PHASE_OTHER
    return to_phase in _LEGAL_EDGES.get(key, frozenset())


def assert_legal_transition(from_phase: str, to_phase: str) -> None:
    """Raise IllegalSettlementTransition with a useful message if illegal."""
    if not is_legal_transition(from_phase, to_phase):
        raise IllegalSettlementTransition(
            f"Illegal settlement transition: {from_phase!r} -> {to_phase!r}"
        )


def legal_next_phases(from_phase: str) -> list[str]:
    """Sorted list of phases reachable in one step (useful for dashboards)."""
    key = from_phase if from_phase in _LEGAL_EDGES else PHASE_OTHER
    return sorted(_LEGAL_EDGES.get(key, frozenset()))


__all__ = [
    "IllegalSettlementTransition",
    "is_legal_transition",
    "assert_legal_transition",
    "legal_next_phases",
]
