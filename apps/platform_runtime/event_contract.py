"""
Canonical view of a persisted platform event row for APIs, webhooks, and operators.

Unified contract fields:

- **event_id** — log primary key (also mirrored into ``payload.event_id`` after publish).
- **event_type** — catalog event name.
- **tenant_id** / **school_id** — scope columns on ``PlatformEventLog``.
- **actor**, **source**, **correlation_id** — optional; carried in ``payload`` when set.
- **payload** — persisted JSON (public fan-out body).
- **created_at** — row timestamp.
- **idempotency_key** — dedupe hint when provided at emit time.
"""

from __future__ import annotations

from typing import Any, Dict


def platform_event_to_contract(row: Any) -> Dict[str, Any]:
    """Return a unified dict including optional payload fields for actor/source/correlation."""
    payload = dict(row.payload) if isinstance(getattr(row, "payload", None), dict) else {}
    created = getattr(row, "created_at", None)
    return {
        "event_id": getattr(row, "pk", None),
        "event_type": getattr(row, "event_type", "") or "",
        "tenant_id": getattr(row, "tenant_id", None) or None,
        "school_id": getattr(row, "school_id", None) or None,
        "actor": payload.get("actor"),
        "source": payload.get("source"),
        "payload": payload,
        "created_at": created.isoformat() if created is not None else None,
        "idempotency_key": getattr(row, "idempotency_key", None) or None,
        "correlation_id": payload.get("correlation_id"),
    }
