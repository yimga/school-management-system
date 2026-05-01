"""
Platform loop slice: attendance_saved platform event → visual workflows → trace logging.

Registered from AppConfig.ready via register_platform_loop_attendance_subscriber().
Workflow dispatch is skipped on replay (is_replay=True) to avoid duplicate side effects;
webhook deliveries remain deduped by (subscription, platform_event) in event_bus.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


def _resolve_school_uuid(raw: Any):
    if raw is None:
        return None
    try:
        return UUID(str(raw).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def on_attendance_saved_platform_loop(payload: dict[str, Any], **kwargs: Any) -> None:
    """Subscriber: domain workflows + analytics trace row."""
    from apps.platform_runtime.events import emit_platform_event

    event_id = kwargs.get("event_id")
    is_replay = bool(kwargs.get("is_replay"))
    raw_school = payload.get("school_id")
    if raw_school is None:
        raw_school = kwargs.get("school_id")
    school_uuid = _resolve_school_uuid(raw_school)
    if school_uuid is None:
        return

    from apps.schools.models import School

    school = School.objects.filter(pk=school_uuid).first()
    if school is None:
        return

    ctx = dict(payload) if isinstance(payload, dict) else {}
    ctx["platform_event_id"] = event_id
    ctx["is_replay"] = is_replay

    bundle_len = 0
    if not is_replay:
        try:
            from apps.siteconfig.workflow_triggers import dispatch_domain_triggers_safe

            bundle = dispatch_domain_triggers_safe(
                school, "attendance_saved", ctx
            ) or {}
            visual = bundle.get("visual_workflows") or []
            bundle_len = len(visual)
        except Exception:
            logger.exception("attendance_saved workflow dispatch failed")
    try:
        emit_platform_event(
            "platform_loop_attendance_trace",
            {
                "source_event_id": str(event_id) if event_id is not None else "",
                "school_id": str(school.pk),
                "status": payload.get("status") if isinstance(payload, dict) else "",
                "is_replay": is_replay,
                "workflow_dispatch_ran": not is_replay,
                "visual_workflow_results": bundle_len,
            },
            tenant_id=str(school.pk),
            school_id=school.pk,
            idempotency_key=(
                f"platform_loop_trace:{event_id}:{'r' if is_replay else 'n'}"[:120]
            ),
        )
    except Exception:
        logger.debug("platform_loop_attendance_trace emit skipped", exc_info=True)


def register_platform_loop_attendance_subscriber() -> None:
    from apps.platform_runtime.event_bus import register_subscriber

    register_subscriber("attendance_saved", on_attendance_saved_platform_loop)
