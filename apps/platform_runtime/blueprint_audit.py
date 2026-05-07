"""Audit helpers for blueprint marketplace actions."""

from __future__ import annotations

from typing import Any

from apps.platform_runtime.events import emit_platform_event


def audit_blueprint_event(
    event_type: str,
    *,
    blueprint_key: str,
    school=None,
    actor=None,
    result: str = "ok",
    reason: str = "",
    installation_id: int | None = None,
    payload: dict[str, Any] | None = None,
):
    school_id = getattr(school, "pk", None)
    actor_id = getattr(actor, "pk", None)
    body = {
        "blueprint_key": blueprint_key,
        "actor_id": actor_id,
        "school_id": str(school_id) if school_id is not None else "",
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
        tenant_id=str(school_id) if school_id is not None else None,
        school_id=school_id,
        idempotency_key=f"{event_type}:{blueprint_key}:{school_id or 'platform'}:{installation_id or ''}:{actor_id or ''}"[:128],
    )
