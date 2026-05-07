"""Audit helpers for pack installation actions."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.events import emit_platform_event


def audit_pack_event(
    event_type: str,
    *,
    pack_key: str,
    pack_type: str,
    school=None,
    actor=None,
    result: str = "ok",
    reason: str = "",
    installation_id: int | None = None,
    payload: dict[str, Any] | None = None,
):
    body = {
        "pack_key": pack_key,
        "pack_type": pack_type,
        "actor_id": getattr(actor, "pk", None),
        "school_id": str(getattr(school, "pk", "") or ""),
        "action": event_type,
        "result": result,
        "reason": reason,
    }
    if installation_id is not None:
        body["installation_id"] = installation_id
    if payload:
        body.update(payload)
    return emit_platform_event(
        event_type,
        body,
        tenant_id=str(getattr(school, "pk", "") or "") or None,
        school_id=getattr(school, "pk", None),
        idempotency_key=f"{event_type}:{pack_key}:{getattr(school, 'pk', '')}:{installation_id or ''}:{getattr(actor, 'pk', '')}",
    )
