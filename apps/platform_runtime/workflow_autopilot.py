"""Autopilot policies, apply logging, and promotion after repeated successes."""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

_PROMOTION_THRESHOLD = 3


def policy_allows_auto_fix(
    *,
    workflow_key: str,
    auto_fix_kind: str,
    tenant_schema: str = "",
) -> bool:
    try:
        from apps.platform_runtime.models import WorkflowAutopilotPolicy
    except Exception:
        return False

    for scope in (tenant_schema, ""):
        pol = (
            WorkflowAutopilotPolicy.objects.filter(
                workflow_key=workflow_key[:80],
                tenant_schema=scope,
                enabled=True,
            )
            .first()
        )
        if pol is None:
            continue
        kinds = pol.allowed_auto_fix_kinds or []
        if auto_fix_kind in kinds:
            return True
    return False


def record_apply_log(
    *,
    run_id: int,
    workflow_key: str,
    auto_fix_kind: str,
    outcome: str,
    actor_user_id: str = "",
    autopilot: bool = False,
) -> None:
    try:
        from apps.platform_runtime.models import WorkflowAutopilotApplyLog

        WorkflowAutopilotApplyLog.objects.create(
            run_id=run_id,
            workflow_key=workflow_key[:80],
            auto_fix_kind=auto_fix_kind[:64],
            outcome=outcome[:32],
            actor_user_id=str(actor_user_id or "")[:40],
            autopilot=autopilot,
        )
    except Exception:
        logger.debug("workflow_autopilot_apply_log_failed", exc_info=True)


def promotion_hint(*, workflow_key: str, auto_fix_kind: str) -> Optional[dict[str, Any]]:
    """If this kind succeeded enough times, suggest enabling autopilot."""

    try:
        from apps.platform_runtime.models import WorkflowAutopilotApplyLog, WorkflowAutopilotPolicy
    except Exception:
        return None

    successes = WorkflowAutopilotApplyLog.objects.filter(
        workflow_key=workflow_key[:80],
        auto_fix_kind=auto_fix_kind[:64],
        outcome="applied",
    ).count()
    if successes < _PROMOTION_THRESHOLD:
        return None
    pol = WorkflowAutopilotPolicy.objects.filter(
        workflow_key=workflow_key[:80],
        tenant_schema="",
        enabled=True,
    ).first()
    if pol and auto_fix_kind in (pol.allowed_auto_fix_kinds or []):
        return None
    return {
        "promote_autopilot": True,
        "workflow_key": workflow_key,
        "auto_fix_kind": auto_fix_kind,
        "success_count": successes,
        "message": (
            f"This fix succeeded {successes} times. Enable autopilot for "
            f"「{auto_fix_kind}」 on this workflow?"
        ),
    }


def try_auto_apply_on_failure(*, run_pk: int) -> bool:
    """After finalize failed with auto_fix_available, apply if policy allows."""

    try:
        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.workflow_fix_handlers import apply_auto_fix_kind
    except Exception:
        return False

    run = WorkflowRun.objects.filter(pk=run_pk).first()  # tenant-isolation-allow: workflow-run-load-by-primary-key-row
    if run is None:
        return False
    remediation = run.suggested_remediation or {}
    if not remediation.get("auto_fix_available"):
        return False
    kind = str(remediation.get("auto_fix_kind", "") or "")
    if not kind:
        return False
    if not policy_allows_auto_fix(
        workflow_key=run.workflow_key,
        auto_fix_kind=kind,
        tenant_schema=run.tenant_schema or "",
    ):
        return False
    result = apply_auto_fix_kind(run=run, kind=kind)
    if result.get("ok"):
        record_apply_log(
            run_id=run.pk,
            workflow_key=run.workflow_key,
            auto_fix_kind=kind,
            outcome="applied",
            autopilot=True,
        )
        return True
    return False


# --- Unattended remediation for STUCK runs (v4.04) --------------------------
# Bounds the stuck -> requeue -> stuck loop. Each requeue spawns a fresh run, so
# we count autopilot applies by (workflow_key, school_id) over a window rather
# than a single pk. Safe-by-default: no enabling policy => shadow (no mutation).
_STUCK_MAX_AUTO_ATTEMPTS = 3
_STUCK_WINDOW_SECONDS = 3600


def _recent_stuck_auto_attempts(run: Any) -> int:
    """Count autopilot applies for this run's school+workflow within the window."""

    try:
        from datetime import timedelta

        from django.utils import timezone

        from apps.platform_runtime.models import (
            WorkflowAutopilotApplyLog,
            WorkflowRun,
        )
    except Exception:
        return 0

    school_id = str(getattr(run, "school_id", "") or "")
    if school_id:
        window_start = timezone.now() - timedelta(seconds=_STUCK_WINDOW_SECONDS)
        run_ids = list(
            # tenant-isolation-allow: autopilot-circuit-breaker-school-scoped-count
            WorkflowRun.objects.filter(
                workflow_key=run.workflow_key,
                school_id=school_id,
                started_at__gte=window_start,
            ).values_list("pk", flat=True)
        )
    else:
        run_ids = [run.pk]
    if not run_ids:
        return 0
    return WorkflowAutopilotApplyLog.objects.filter(
        autopilot=True,
        outcome="applied",
        workflow_key=run.workflow_key[:80],
        run_id__in=run_ids,
    ).count()


def try_auto_apply_on_stuck(*, run_pk: int) -> dict[str, Any]:
    """Unattended remediation for a STUCK run, gated by WorkflowAutopilotPolicy.

    Safe-by-default: with no enabling policy this only proposes (``shadow``) and
    mutates nothing. When the policy enables the kind it applies the same narrow,
    idempotent handler the manual Retry button uses, bounded by a per-school
    circuit breaker, and logs every outcome to WorkflowAutopilotApplyLog.
    """

    try:
        from apps.platform_runtime.models import WorkflowRun
        from apps.platform_runtime.workflow_fix_handlers import (
            STUCK_DEFAULT_FIX_BY_WORKFLOW,
            apply_auto_fix_kind,
        )
    except Exception:
        return {"applied": False, "reason": "import_failed"}

    run = WorkflowRun.objects.filter(pk=run_pk).first()  # tenant-isolation-allow: workflow-run-load-by-primary-key-row
    if run is None:
        return {"applied": False, "reason": "run_not_found"}
    if getattr(run, "status", "") != "stuck":
        return {"applied": False, "reason": "not_stuck"}

    remediation = run.suggested_remediation or {}
    kind = str(remediation.get("auto_fix_kind", "") or "") or STUCK_DEFAULT_FIX_BY_WORKFLOW.get(
        run.workflow_key, ""
    )
    if not kind:
        return {"applied": False, "reason": "no_fix_kind"}

    if not policy_allows_auto_fix(
        workflow_key=run.workflow_key,
        auto_fix_kind=kind,
        tenant_schema=run.tenant_schema or "",
    ):
        record_apply_log(
            run_id=run.pk,
            workflow_key=run.workflow_key,
            auto_fix_kind=kind,
            outcome="shadow",
            autopilot=True,
        )
        return {"applied": False, "reason": "policy_disabled", "mode": "shadow", "kind": kind}

    if _recent_stuck_auto_attempts(run) >= _STUCK_MAX_AUTO_ATTEMPTS:
        record_apply_log(
            run_id=run.pk,
            workflow_key=run.workflow_key,
            auto_fix_kind=kind,
            outcome="circuit_open",
            autopilot=True,
        )
        return {"applied": False, "reason": "circuit_open", "kind": kind}

    result = apply_auto_fix_kind(run=run, kind=kind)
    ok = bool(result.get("ok"))
    record_apply_log(
        run_id=run.pk,
        workflow_key=run.workflow_key,
        auto_fix_kind=kind,
        outcome="applied" if ok else "failed",
        autopilot=True,
    )
    return {"applied": ok, "kind": kind, "mode": "apply", "result": result}
