"""Structured audit events for AI Center (no secrets in payloads)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

logger = logging.getLogger("runmycampus.ai_center.audit")

AI_CENTER_EVENT_TYPES = frozenset(
    {
        "ai_query_submitted",
        "ai_answer_generated",
        "ai_missing_context",
        "ai_feature_absent",
        "ai_kb_draft_created",
        "ai_kb_draft_published",
        "ai_contextual_tip_generated",
        "ai_friction_topic_detected",
        "ai_gateway_error",
        "ai_gateway_disabled_fallback",
    }
)


def emit_ai_center_event(
    event_type: str,
    *,
    audit_id: str | None = None,
    tenant_id: str | None = None,
    user_id: str | None = None,
    route_context: str | None = None,
    payload_summary: dict[str, Any] | None = None,
) -> str:
    """
    Best-effort structured log; returns audit_id (UUID hex).
    Never raises — audit failure must not break request paths.
    """
    if event_type not in AI_CENTER_EVENT_TYPES:
        logger.warning("unknown ai_center event_type=%s", event_type)
    aid = audit_id or uuid.uuid4().hex
    safe_payload: dict[str, Any] = {}
    for key, val in (payload_summary or {}).items():
        if any(s in key.lower() for s in ("password", "secret", "token", "key", "email")):
            continue
        if isinstance(val, str) and len(val) > 256:
            safe_payload[key] = val[:256] + "…"
        else:
            safe_payload[key] = val
    try:
        from apps.observability.metrics import emit_counter

        emit_counter(
            "ai_center_event_total",
            labels={"event_type": event_type},
        )
    except Exception:
        pass
    logger.info(
        "ai_center_event",
        extra={
            "event_type": event_type,
            "audit_id": aid,
            "tenant_id": tenant_id,
            "user_id": user_id,
            "route_context": (route_context or "")[:120],
            "payload_summary": safe_payload,
        },
    )
    return aid
