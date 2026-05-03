"""
Ledger-facing settlement phases (honest naming — never implies paid without confirmation).

Maps ``MarketplaceMonetizationLedgerEntry.event_type`` values to canonical settlement_phase labels.
"""

from __future__ import annotations

from typing import Any

from apps.marketplace.models import MarketplaceMonetizationLedgerEntry

# Canonical phases referenced by dashboards / APIs (stringstable).
PHASE_SETTLEMENT_PENDING = "settlement_pending"
PHASE_SETTLEMENT_EXTERNAL_BLOCKED = "settlement_external_blocked"
PHASE_SETTLEMENT_READY = "settlement_ready"
PHASE_SETTLEMENT_PAID = "settlement_paid"
PHASE_SETTLEMENT_FAILED = "settlement_failed"
PHASE_SETTLEMENT_RECONCILED = "settlement_reconciled"
PHASE_OTHER = "other"

EVENT_TO_PHASE: dict[str, str] = {
    MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_PENDING: PHASE_SETTLEMENT_PENDING,
    MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_PENDING_EXTERNAL: PHASE_SETTLEMENT_PENDING,
    MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_READY: PHASE_SETTLEMENT_READY,
    MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_EXTERNAL_BLOCKED: PHASE_SETTLEMENT_EXTERNAL_BLOCKED,
    MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_COMPLETED: PHASE_SETTLEMENT_PAID,
    MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_FAILED: PHASE_SETTLEMENT_FAILED,
    MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_RECONCILED: PHASE_SETTLEMENT_RECONCILED,
}


def settlement_phase_for_event(event_type: str) -> str:
    return EVENT_TO_PHASE.get(event_type or "", PHASE_OTHER)


def blocked_settlement_reason_from_entry(entry: Any | None) -> str:
    """Human-readable blocker line from ledger metadata (no secrets)."""
    if entry is None:
        return ""
    md = getattr(entry, "metadata", None) or {}
    if not isinstance(md, dict):
        return ""
    reason = md.get("reason") or md.get("blocked_reason") or ""
    tier = md.get("readiness_tier") or ""
    bits = [str(x).strip() for x in (reason, tier) if str(x).strip()]
    return " — ".join(bits) if bits else ""
