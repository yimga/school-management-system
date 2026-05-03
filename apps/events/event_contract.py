"""
Unified serialization for :class:`~apps.events.models.DomainEvent` rows (operator console).

Aligns shape with :func:`apps.platform_runtime.event_contract.platform_event_to_contract`
without migrating historical payloads.
"""

from __future__ import annotations

from typing import Any


def domain_event_to_contract(ev: Any) -> dict[str, Any]:
    """Map DomainEvent ORM row to a stable operator-facing dict."""
    payload = dict(ev.payload) if isinstance(getattr(ev, "payload", None), dict) else {}
    created = getattr(ev, "created_at", None)
    sid = getattr(ev, "school_id", None)
    return {
        "event_id": str(getattr(ev, "id", "") or ""),
        "event_type": str(getattr(ev, "event_type", "") or ""),
        "school_id": str(sid) if sid is not None else None,
        "tenant_id": str(sid) if sid is not None else None,
        "schema_name": getattr(ev, "schema_name", None) or None,
        "actor": payload.get("actor"),
        "source": payload.get("source"),
        "payload": payload,
        "created_at": created.isoformat() if created is not None else None,
        "idempotency_key": getattr(ev, "idempotency_key", None) or None,
        "correlation_id": payload.get("correlation_id"),
        "status": getattr(ev, "status", None),
        "storage": "domain_outbox",
    }


def payload_summary(payload: dict[str, Any] | None, *, max_keys: int = 12) -> str:
    """Short JSON-ish summary for list rows (avoid huge blobs)."""
    if not isinstance(payload, dict) or not payload:
        return "{}"
    keys = sorted(payload.keys())
    trimmed = {k: payload[k] for k in keys[:max_keys]}
    hint = "…" if len(keys) > max_keys else ""
    try:
        import json

        return json.dumps(trimmed, default=str, sort_keys=True) + hint
    except (TypeError, ValueError):
        return str(trimmed) + hint
