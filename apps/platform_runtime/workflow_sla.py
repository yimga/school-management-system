"""SLA breach detection from registry slo_seconds."""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


def slo_seconds_for_key(workflow_key: str) -> int:
    try:
        from apps.platform_runtime.workflow_registry import WORKFLOWS

        definition = WORKFLOWS.get(workflow_key or "")
        if definition is None:
            return 0
        return max(int(getattr(definition, "slo_seconds", 0) or 0), 0)
    except Exception:
        return 0


def publish_sla_breach_event(*, run: Any, slo_seconds: int, actual_seconds: int) -> None:
    """Operator alert via platform event bus + email matrix (cooldown per recipient)."""

    try:
        from apps.platform_runtime.event_bus import publish_event

        publish_event(
            "workflow.sla.breached",
            {
                "run_id": int(run.pk),
                "workflow_key": str(getattr(run, "workflow_key", "") or ""),
                "workflow_label": str(getattr(run, "workflow_label", "") or ""),
                "tenant_schema": str(getattr(run, "tenant_schema", "") or ""),
                "slo_seconds": slo_seconds,
                "actual_seconds": actual_seconds,
                "status": str(getattr(run, "status", "") or ""),
                "current_step_name": str(getattr(run, "current_step_name", "") or ""),
            },
            strict_catalog=True,
            source="platform_runtime.workflow_sla",
        )
    except Exception:
        logger.warning("workflow_sla_breach_event_publish_failed", exc_info=True)


def maybe_record_sla_breach(*, run: Any, actual_seconds: int) -> bool:
    slo = slo_seconds_for_key(str(getattr(run, "workflow_key", "") or ""))
    if slo <= 0 or actual_seconds <= slo:
        return False
    try:
        from apps.platform_runtime.models import WorkflowSlaBreach

        run_id = int(run.pk)
        if WorkflowSlaBreach.objects.filter(run_id=run_id).exists():
            return False
        WorkflowSlaBreach.objects.create(
            run_id=run_id,
            workflow_key=str(run.workflow_key or "")[:80],
            tenant_schema=str(getattr(run, "tenant_schema", "") or "")[:64],
            slo_seconds=slo,
            actual_seconds=min(actual_seconds, 86400),  # magic-number-allow: sla-actual-cap
        )
        publish_sla_breach_event(run=run, slo_seconds=slo, actual_seconds=actual_seconds)
        return True
    except Exception:
        logger.debug("workflow_sla_breach_record_failed", exc_info=True)
        return False


def record_running_sla_breach_if_needed(*, run: Any) -> bool:
    """While still running, record + notify once when age exceeds registry SLO."""

    meta = sla_meta_for_run(run)
    if not meta.get("slo_breached"):
        return False
    age = int(meta.get("age_seconds") or 0)
    return maybe_record_sla_breach(run=run, actual_seconds=age)


def sla_meta_for_run(run: Any) -> dict[str, Any]:
    slo = slo_seconds_for_key(str(getattr(run, "workflow_key", "") or ""))
    if slo <= 0:
        return {}
    started = getattr(run, "started_at", None)
    age = 0
    if started is not None:
        try:
            age = max(0, int((timezone.now() - started).total_seconds()))
        except Exception:
            age = 0
    return {
        "slo_seconds": slo,
        "age_seconds": age,
        "slo_breached": age > slo and getattr(run, "status", "") == "running",
    }
