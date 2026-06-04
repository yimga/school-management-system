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
