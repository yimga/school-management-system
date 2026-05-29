"""Fractional room / instructor capacity helpers (Phase 4E)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any


def _as_decimal(value: Any, default: str = "1") -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(default)


def effective_room_capacity(room: Any, *, utilization_fraction: Decimal | None = None) -> Decimal:
    """
    Compute usable seats for a room with optional fractional utilization.

    ``utilization_fraction`` defaults to ``room.capacity_fraction`` when present,
    otherwise ``1.00`` (full room).
    """
    base = _as_decimal(getattr(room, "capacity", 0) or 0, "0")
    fraction = utilization_fraction
    if fraction is None:
        fraction = _as_decimal(getattr(room, "capacity_fraction", None), "1")
    if fraction <= Decimal("0"):
        return Decimal("0")
    if fraction > Decimal("1"):
        fraction = Decimal("1")
    return (base * fraction).quantize(Decimal("0.01"))


def cross_campus_allocation_ok(
    *,
    existing_fraction: Decimal,
    requested_fraction: Decimal,
    max_fraction: Decimal = Decimal("1"),
) -> bool:
    """Return True when combined fractional allocation stays within ``max_fraction``."""
    total = existing_fraction + requested_fraction
    return total <= max_fraction
