"""Bridge canonical domain events (outbox) to ``trigger_dispatcher.fire``.

``dispatch_domain_triggers_safe`` already runs visual/school workflows from product
signals; this module ensures every processed :class:`~apps.events.models.DomainEvent`
also hits the auditable trigger registry (batch 1227 bus-boundary follow-up).
"""

from __future__ import annotations

import logging
from typing import Any

from apps.automation.trigger_dispatcher import fire
from apps.automation.workflow_trigger_catalog import FULL_TRIGGER_CATALOG_KEYS

logger = logging.getLogger(__name__)

from apps.automation.workflow_limits import MAX_DOMAIN_EVENT_CHAIN_DEPTH

_DOMAIN_EVENT_DEDUP_TTL_SECONDS = 86_400

# Domain event_type may differ from workflow trigger keys (aliases).
_EVENT_TYPE_TO_TRIGGER: dict[str, str] = {
    "attendance_saved": "attendance_saved",
    "attendance.saved": "attendance_saved",
    "payment_success": "payment_success",
    "payment.success": "payment_success",
    "payment_received": "payment_success",
    "payment_failed": "payment_failed",
    "payment.failed": "payment_failed",
    "report_generated": "report_generated",
    "marks_submitted": "marks_submitted",
    "grade_submitted": "marks_submitted",
    "student_risk_detected": "student_risk_detected",
    "app_installed": "app_installed",
    "offline_action_conflict": "offline_action_conflict",
}


def resolve_trigger_key(event_type: str) -> str | None:
    et = (event_type or "").strip()
    if not et:
        return None
    if et in FULL_TRIGGER_CATALOG_KEYS:
        return et
    return _EVENT_TYPE_TO_TRIGGER.get(et)


def _domain_event_already_dispatched(domain_event_id: Any) -> bool:
    if not domain_event_id:
        return False
    try:
        from django.core.cache import cache
    except ImportError:
        return False
    key = f"rmc:v1:domain_event_dispatched:{domain_event_id}"
    if cache.get(key):
        return True
    cache.set(key, "1", timeout=_DOMAIN_EVENT_DEDUP_TTL_SECONDS)
    return False


def dispatch_domain_event_to_triggers(domain_event: Any) -> list[dict[str, Any]]:
    """Map a persisted domain event to ``fire()`` when the type is known."""
    if _domain_event_already_dispatched(getattr(domain_event, "pk", None)):
        return []

    trigger_key = resolve_trigger_key(str(getattr(domain_event, "event_type", "") or ""))
    if not trigger_key:
        return []

    school_id = getattr(domain_event, "school_id", None)
    if not school_id:
        return []

    from apps.schools.models import School

    school = School.objects.filter(pk=school_id).first()
    if school is None:
        return []

    payload = getattr(domain_event, "payload", None)
    if not isinstance(payload, dict):
        payload = {}

    depth_raw = payload.get("_domain_event_depth", 0)
    try:
        depth = int(depth_raw)
    except (TypeError, ValueError):
        depth = 0
    if depth > MAX_DOMAIN_EVENT_CHAIN_DEPTH:
        logger.warning(
            "domain_event_bridge: depth limit event_type=%s school=%s depth=%s",
            getattr(domain_event, "event_type", ""),
            school.pk,
            depth,
        )
        return []

    ctx = dict(payload)
    ctx["_domain_event_depth"] = depth + 1
    ctx.setdefault("domain_event_id", str(getattr(domain_event, "pk", "") or ""))
    ctx.setdefault("school_id", str(school.pk))

    try:
        return fire(trigger_key, ctx, school=school, actor=None)
    except Exception:
        logger.exception(
            "domain_event_bridge: trigger dispatch failed event_type=%s school=%s",
            getattr(domain_event, "event_type", ""),
            school.pk,
        )
        return []


def register_domain_event_trigger_subscriber() -> None:
    from apps.events.bus import subscribe

    subscribe("*", _on_domain_event)


def _on_domain_event(domain_event: Any) -> None:
    dispatch_domain_event_to_triggers(domain_event)


__all__ = [
    "dispatch_domain_event_to_triggers",
    "register_domain_event_trigger_subscriber",
    "resolve_trigger_key",
]
