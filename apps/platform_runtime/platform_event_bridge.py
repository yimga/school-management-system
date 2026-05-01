"""
Subscriber hooks for downstream surfaces (AI recommendation refresh placeholder, etc.).
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def register_platform_event_ai_bridge() -> None:
    """Register a wildcard subscriber that forwards metadata to the AI layer hook (non-blocking)."""

    def _on_any(payload, event_type=None, school_id=None, **kwargs):
        try:
            from apps.platform_runtime.ai_system_layer import create_ai_recommendation_record

            create_ai_recommendation_record(
                {
                    "event_type": event_type,
                    "school_id": school_id,
                    "payload_sample_keys": list((payload or {}).keys())[:30],
                }
            )
        except Exception:
            logger.debug("platform_event_ai_bridge skipped", exc_info=True)

    try:
        from apps.platform_runtime.event_bus import register_subscriber

        register_subscriber("*", _on_any)
    except Exception:
        logger.debug("register_platform_event_ai_bridge failed", exc_info=True)


def register_platform_event_analytics_bridge() -> None:
    """
    Record high-signal platform bus events into FeatureUsageEvent (tenant analytics).
    Skips noisy/internal trace types.
    """

    def _on(payload, event_type=None, school_id=None, tenant_id=None, **kwargs):
        et = (event_type or "").strip()
        if not et or et == "platform_event_replayed":
            return
        if et.startswith("platform_loop_") or et.startswith("celery_task_"):
            return
        raw_sid = school_id or tenant_id
        if raw_sid is None and isinstance(payload, dict):
            raw_sid = payload.get("school_id") or payload.get("_school_id")
        if raw_sid is None:
            return
        try:
            from apps.schools.models import School

            sch = School.objects.filter(pk=raw_sid).first()
            if sch is None:
                try:
                    sch = School.objects.filter(pk=int(str(raw_sid))).first()
                except (TypeError, ValueError):
                    sch = None
            if sch is None:
                return
            from apps.siteconfig.feature_usage import track_event

            track_event(f"platform_bus:{et}", school=sch, user=None)
        except Exception:
            logger.debug("platform_event_analytics_bridge skipped", exc_info=True)

    try:
        from apps.platform_runtime.event_bus import register_subscriber

        register_subscriber("*", _on)
    except Exception:
        logger.debug("register_platform_event_analytics_bridge failed", exc_info=True)
