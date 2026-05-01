"""
Executor for relational :class:`~apps.automation.workflow_graph_models.Workflow`.

Uses ``siteconfig.workflow_engine`` for conditions/actions and writes ``WorkflowRunLog``.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any

from django.apps import apps

logger = logging.getLogger(__name__)

_SOFT = (
    AttributeError,
    ImportError,
    LookupError,
    RuntimeError,
    TypeError,
    ValueError,
)


def run_workflow(
    workflow_id: int,
    event_payload: dict[str, Any],
    *,
    user=None,
    dry_run: bool = False,
) -> dict[str, Any]:
    """
    Evaluate compiled graph DSL for one workflow run.

    ``event_payload`` is merged with ``_workflow_id`` for action handlers.
    """
    Workflow = apps.get_model("automation", "Workflow")
    WorkflowRunLog = apps.get_model("automation", "WorkflowRunLog")

    wf = Workflow.objects.select_related("school").filter(pk=workflow_id).first()
    if wf is None:
        return {"ok": False, "error": "workflow_not_found"}
    # Live runs require published; dry-run allows draft for designer simulation.
    if not dry_run and wf.status != Workflow.Status.PUBLISHED:
        return {"ok": False, "error": "workflow_not_published"}
    if not wf.is_active:
        return {"ok": False, "error": "workflow_inactive"}

    school = wf.school
    trig_token = ""

    def _emit_platform_workflow_triggered() -> None:
        nonlocal trig_token
        try:
            from apps.platform_runtime.event_bus import publish_event

            trig_token = secrets.token_hex(8)
            publish_event(
                "workflow_triggered",
                {
                    "workflow_id": wf.pk,
                    "trigger_event": str(wf.trigger_event),
                    "source": "visual_executor",
                },
                tenant_id=str(school.pk),
                school_id=school.pk,
                idempotency_key=f"wf_trig:{wf.pk}:{trig_token}",
            )
        except _SOFT:
            logger.debug("workflow_triggered publish skipped", exc_info=True)

    def _emit_platform_workflow_completed(
        log,
        *,
        conditions_passed: bool | None,
    ) -> None:
        try:
            from apps.platform_runtime.event_bus import publish_event

            lid = getattr(log, "pk", None) if log is not None else None
            st = getattr(log, "status", None) if log is not None else None
            publish_event(
                "workflow_completed",
                {
                    "workflow_id": wf.pk,
                    "workflow_run_log_id": lid,
                    "status": str(st) if st is not None else "unknown",
                    "trigger_event": str(wf.trigger_event),
                    "conditions_passed": conditions_passed,
                },
                tenant_id=str(school.pk),
                school_id=school.pk,
                idempotency_key=(
                    f"wf_done:{lid}" if lid else f"wf_done:{wf.pk}:{trig_token or secrets.token_hex(4)}"
                )[:128],
            )
        except _SOFT:
            logger.debug("workflow_completed publish skipped", exc_info=True)

    try:
        from apps.automation.graph_compiler import compile_workflow_to_dsl

        dsl = compile_workflow_to_dsl(wf)
        from apps.siteconfig.workflow_engine import (
            evaluate_conditions,
            run_actions,
            sanitize_workflow_context_for_storage,
            simulate_dsl,
        )

        ctx = dict(event_payload) if isinstance(event_payload, dict) else {}
        ctx["_workflow_id"] = wf.pk

        if dry_run:
            prev = simulate_dsl(dsl, ctx, school=school, user=user)
            return {"ok": True, "dry_run": True, **prev}

        _emit_platform_workflow_triggered()

        conditions_passed = evaluate_conditions(dsl.get("conditions") or [], ctx)
        if not conditions_passed:
            log = None
            try:
                log = WorkflowRunLog.objects.create(
                    workflow=wf,
                    trigger_event=wf.trigger_event,
                    conditions_passed=False,
                    dry_run=False,
                    payload_snapshot=sanitize_workflow_context_for_storage(ctx),
                    actions_run=[],
                    status=WorkflowRunLog.Status.SKIPPED,
                    triggered_by=user,
                )
            except _SOFT as e:
                logger.warning("WorkflowRunLog skip write failed: %s", e)
            _emit_platform_workflow_completed(log, conditions_passed=False)
            return {
                "ok": True,
                "conditions_passed": False,
                "actions_run": [],
                "audit_ref": str(log.pk) if log else "",
                "workflow_id": wf.pk,
            }

        actions_run = run_actions(
            dsl.get("actions") or [],
            ctx,
            school=school,
            dry_run=False,
            user=user,
        )
        failed = [r for r in actions_run if isinstance(r, dict) and r.get("error")]
        log = None
        try:
            log = WorkflowRunLog.objects.create(
                workflow=wf,
                trigger_event=wf.trigger_event,
                conditions_passed=True,
                dry_run=False,
                payload_snapshot=sanitize_workflow_context_for_storage(ctx),
                actions_run=actions_run,
                status=(
                    WorkflowRunLog.Status.FAILED
                    if failed
                    else WorkflowRunLog.Status.SUCCESS
                ),
                error_message=(failed[0].get("error", "")[:2000] if failed else ""),
                triggered_by=user,
            )
        except _SOFT as e:
            logger.warning("WorkflowRunLog write failed: %s", e)

        _emit_platform_workflow_completed(log, conditions_passed=True)

        return {
            "ok": True,
            "conditions_passed": True,
            "actions_run": actions_run,
            "audit_ref": str(log.pk) if log else "",
            "workflow_id": wf.pk,
        }
    except _SOFT as e:
        logger.warning("run_workflow failed wf=%s: %s", workflow_id, e)
        return {"ok": False, "error": str(e)}


def run_matching_visual_workflows(
    school,
    trigger_type: str,
    context: dict[str, Any],
    *,
    user=None,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Run all published active visual workflows whose trigger matches ``trigger_type``."""
    Workflow = apps.get_model("automation", "Workflow")

    qs = Workflow.objects.filter(
        school=school,
        is_active=True,
        status=Workflow.Status.PUBLISHED,
        trigger_event=trigger_type,
    )
    out: list[dict[str, Any]] = []
    for wf in qs:
        try:
            r = run_workflow(wf.pk, context, user=user, dry_run=dry_run)
            out.append({"workflow_id": wf.pk, **r})
        except _SOFT as e:
            out.append({"workflow_id": wf.pk, "ok": False, "error": str(e)})
    return out


def simulate_workflow(workflow_id: int, sample_payload: dict[str, Any], *, user=None):
    """Preview conditions + dry-run actions (no side effects)."""
    return run_workflow(workflow_id, sample_payload, user=user, dry_run=True)
