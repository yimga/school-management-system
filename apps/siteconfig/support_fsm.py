"""v4.00.42 — Status FSM hard-enforcement for GlobalSupportTicket.

Defines the allowed status transitions and validates them. The previous
``support_bulk_action`` endpoint applied any transition without checking
whether it made sense (CLOSED -> OPEN, RESOLVED -> WAITING, etc.). This
module is the single source of truth.

Use cases:
  - ``can_transition(from_status, to_status) -> bool`` for guard checks.
  - ``validate_transition(from_status, to_status)`` raises ``InvalidTransition``
    on bad jumps so callers can return a typed 400.

Reopen path: CLOSED -> OPEN and RESOLVED -> OPEN are explicitly allowed
because tenants can submit a follow-up that revives the ticket.
"""

from __future__ import annotations

from typing import Iterable


class InvalidTransition(ValueError):
    """Raised when a caller tries to apply an unsupported status transition."""


# Forward graph: { from_status: {allowed_next_statuses} }
ALLOWED: dict[str, frozenset[str]] = {
    "OPEN": frozenset({"OPEN", "IN_PROGRESS", "WAITING", "RESOLVED", "CLOSED"}),
    "IN_PROGRESS": frozenset({"IN_PROGRESS", "WAITING", "RESOLVED", "CLOSED", "OPEN"}),
    "WAITING": frozenset({"WAITING", "IN_PROGRESS", "RESOLVED", "CLOSED", "OPEN"}),
    "RESOLVED": frozenset({"RESOLVED", "CLOSED", "OPEN", "IN_PROGRESS"}),
    "CLOSED": frozenset({"CLOSED", "OPEN"}),
}


def can_transition(from_status: str, to_status: str) -> bool:
    """Return True if ``from_status`` can move to ``to_status``."""
    allowed = ALLOWED.get((from_status or "").upper())
    if allowed is None:
        return False
    return (to_status or "").upper() in allowed


def validate_transition(from_status: str, to_status: str) -> None:
    """Raise ``InvalidTransition`` if the move is not allowed."""
    if not can_transition(from_status, to_status):
        raise InvalidTransition(
            f"Cannot transition from {from_status!r} to {to_status!r}"
        )


def allowed_next(from_status: str) -> Iterable[str]:
    """Iterable of allowed next statuses for the given current status."""
    return tuple(sorted(ALLOWED.get((from_status or "").upper(), frozenset())))
