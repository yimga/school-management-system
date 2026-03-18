"""
Minimal workflow execution engine (Part 2c). Evaluates conditions and runs actions; logs each run.
"""

import logging
from smtplib import SMTPException

from django.utils import timezone

from apps.platform_runtime.structured_logging import log_exception_with_context

logger = logging.getLogger(__name__)
WORKFLOW_SOFT_FAILURES = (
    AttributeError,
    ImportError,
    LookupError,
    RuntimeError,
    TypeError,
    ValueError,
)


class WorkflowActionExecutionError(RuntimeError):
    """Raised when a workflow action fails but execution should degrade safely."""


def evaluate_conditions(conditions: list, context: dict) -> bool:
    """
    Evaluate a list of conditions against context. Each item: {"field": "...", "op": "eq"|"gt"|..., "value": ...}.
    Returns True if all conditions pass (or list is empty).
    """
    if not conditions:
        return True
    for c in conditions:
        if not isinstance(c, dict):
            continue
        field = c.get("field", "")
        op = (c.get("op") or "eq").lower()
        want = c.get("value")
        actual = context.get(field)
        if op == "eq" and actual != want:
            return False
        if op == "neq" and actual == want:
            return False
        if op == "gt" and not (
            actual is not None and want is not None and actual > want
        ):
            return False
        if op == "gte" and not (
            actual is not None and want is not None and actual >= want
        ):
            return False
        if op == "lt" and not (
            actual is not None and want is not None and actual < want
        ):
            return False
        if op == "lte" and not (
            actual is not None and want is not None and actual <= want
        ):
            return False
        if op == "in" and actual not in (
            want if isinstance(want, (list, tuple)) else []
        ):
            return False
        if op == "contains":
            if want is None:
                continue
            if isinstance(actual, (list, tuple)) and want in actual:
                continue
            if isinstance(actual, str) and isinstance(want, str) and want in actual:
                continue
            return False
    return True


def _run_action_notify(params: dict, context: dict, school=None) -> None:
    """Send notification (email/push/in-app). params: channel, subject, body, recipient_ref (e.g. context key)."""
    channel = (params.get("channel") or "log").lower()
    if channel == "log":
        logger.info("Workflow notify: %s", params.get("body", params))
        return
    if channel == "email" and params.get("to"):
        try:
            from apps.communication.notification_service import send_email

            to_list = (
                [params["to"]] if isinstance(params["to"], str) else list(params["to"])
            )
            send_email(
                to_list,
                subject=params.get("subject", "Notification"),
                body=params.get("body", ""),
                school=school,
                fail_silently=True,
            )
        except (*WORKFLOW_SOFT_FAILURES, SMTPException) as e:
            school_id = (
                str(getattr(school, "pk", None) or getattr(school, "id", None))
                if school
                else None
            )
            log_exception_with_context(
                "workflow_engine: notify email failed",
                school_id=school_id,
                extra={"error": str(e)},
            )
            logger.warning("Workflow notify email failed: %s", e)
            raise WorkflowActionExecutionError(str(e)) from e
    # In-app / push can be wired here via notification backend
    return


def _run_action_emit_event(params: dict, context: dict, school=None) -> None:
    """Emit a domain event. params: event_type, payload (dict or context keys)."""
    try:
        from apps.events.services import emit_event

        event_type = params.get("event_type") or "workflow.triggered"
        payload = dict(params.get("payload") or {})
        for k, v in (context or {}).items():
            if k.startswith("event_"):
                payload[k] = v
        school_id = getattr(school, "pk", None) or getattr(school, "id", None)
        schema_name = getattr(
            getattr(school, "client", None), "schema_name", None
        ) or getattr(school, "schema_name", None)
        emit_event(
            event_type=event_type,
            payload=payload,
            school_id=school_id,
            schema_name=schema_name,
        )
    except WORKFLOW_SOFT_FAILURES as e:
        school_id = (
            str(getattr(school, "pk", None) or getattr(school, "id", None))
            if school
            else None
        )
        log_exception_with_context(
            "workflow_engine: emit_event failed",
            school_id=school_id,
            extra={"error": str(e)},
        )
        logger.warning("Workflow emit_event failed: %s", e)
        raise WorkflowActionExecutionError(str(e)) from e


def run_actions(actions: list, context: dict, school=None) -> list:
    """
    Run action list (e.g. [{"type": "notify", "params": {...}}, {"type": "emit_event", "params": {...}}]).
    Supported types: notify, emit_event. Unknown types are logged only.
    Returns list of results per action for audit.
    24.13: Each action runs in try/except; a failed action records error in result
    and does not abort the rest of the workflow (safe degradation).
    """
    ACTION_HANDLERS = {
        "notify": _run_action_notify,
        "emit_event": _run_action_emit_event,
    }
    results = []
    for a in actions or []:
        if not isinstance(a, dict):
            continue
        action_type = a.get("type", "")
        params = a.get("params") or {}
        try:
            handler = ACTION_HANDLERS.get(action_type)
            if handler:
                handler(params, context, school=school)
            else:
                logger.info(
                    "Workflow action: type=%s params=%s school=%s",
                    action_type,
                    params,
                    getattr(school, "id", None),
                )
            results.append(
                {
                    "type": action_type,
                    "params": params,
                    "run_at": timezone.now().isoformat(),
                }
            )
        except WorkflowActionExecutionError as e:
            school_id = (
                str(getattr(school, "pk", None) or getattr(school, "id", None))
                if school
                else None
            )
            log_exception_with_context(
                "workflow_engine: action failed",
                school_id=school_id,
                extra={"action_type": action_type, "error": str(e)},
            )
            logger.warning("Workflow action failed: type=%s error=%s", action_type, e)
            results.append(
                {
                    "type": action_type,
                    "params": params,
                    "run_at": timezone.now().isoformat(),
                    "error": str(e),
                }
            )
    return results


def get_effective_workflow_dsl(tenant_workflow) -> dict:
    """
    Return the effective workflow DSL (Section 5): trigger, conditions, actions.
    Level 1 (LOCKED): template only, no overrides. Level 2/3: merge template with overrides.
    """
    from .models_workflow import WorkflowTemplate, TenantWorkflow

    if not isinstance(tenant_workflow, TenantWorkflow):
        return {}
    template = getattr(tenant_workflow, "template", None)
    if not template:
        return {}
    overrides = getattr(tenant_workflow, "overrides", None) or {}
    level = getattr(template, "level", None)
    # Level 1 = LOCKED: ignore overrides (safety/legal)
    if level == WorkflowTemplate.Level.LOCKED:
        return {
            "trigger": template.trigger,
            "trigger_config": template.trigger_config or {},
            "conditions": list(template.conditions or []),
            "actions": list(template.actions or []),
        }
    # Level 2/3: merge overrides
    conditions = (
        overrides.get("conditions")
        if isinstance(overrides.get("conditions"), list)
        else (template.conditions or [])
    )
    actions = (
        overrides.get("actions")
        if isinstance(overrides.get("actions"), list)
        else (template.actions or [])
    )
    return {
        "trigger": overrides.get("trigger") or template.trigger,
        "trigger_config": {
            **(template.trigger_config or {}),
            **(overrides.get("trigger_config") or {}),
        },
        "conditions": conditions,
        "actions": actions,
    }


def run_workflow(tenant_workflow, context: dict) -> dict:
    """
    Run a TenantWorkflow: effective DSL (Level 1 = locked, 2/3 = with overrides),
    evaluate conditions, run actions, log (Trigger → Conditions → Actions → Audit).
    Returns {"ok": bool, "conditions_passed": bool, "actions_run": list, "audit_ref": str}.
    """
    from .models_workflow import TenantWorkflow

    if not isinstance(tenant_workflow, TenantWorkflow):
        return {"ok": False, "error": "Invalid TenantWorkflow"}

    template = getattr(tenant_workflow, "template", None)
    if not template or not template.is_active:
        return {"ok": False, "error": "Template inactive or missing"}

    dsl = get_effective_workflow_dsl(tenant_workflow)
    conditions = dsl.get("conditions") or []
    actions = dsl.get("actions") or []

    conditions_passed = evaluate_conditions(conditions, context)
    context_keys = list(context.keys()) if isinstance(context, dict) else []
    if not conditions_passed:
        audit_ref = ""
        try:
            from .models_workflow import WorkflowRunLog

            log = WorkflowRunLog.objects.create(
                tenant_workflow=tenant_workflow,
                conditions_passed=False,
                actions_run=[],
                context_keys=context_keys,
            )
            audit_ref = str(log.id)
        except WORKFLOW_SOFT_FAILURES as e:
            school_id = (
                str(getattr(getattr(tenant_workflow, "school", None), "id", None))
                if getattr(tenant_workflow, "school", None)
                else None
            )
            log_exception_with_context(
                "workflow_engine: WorkflowRunLog create failed (conditions_passed=False)",
                school_id=school_id,
                extra={"error": str(e)},
            )
            logger.warning("WorkflowRunLog create failed: %s", e)
        return {
            "ok": True,
            "conditions_passed": False,
            "actions_run": [],
            "audit_ref": audit_ref,
        }

    school = getattr(tenant_workflow, "school", None)
    actions_run = run_actions(actions, context, school=school)
    try:
        from apps.platform_runtime.governor_limits import record_workflow_run

        record_workflow_run(school_id=getattr(school, "id", None) if school else None)
    except WORKFLOW_SOFT_FAILURES as e:
        logger.debug("record_workflow_run skipped: %s", e)

    audit_ref = ""
    try:
        from .models_workflow import WorkflowRunLog

        log = WorkflowRunLog.objects.create(
            tenant_workflow=tenant_workflow,
            conditions_passed=True,
            actions_run=actions_run,
            context_keys=context_keys,
        )
        audit_ref = str(log.id)
    except WORKFLOW_SOFT_FAILURES as e:
        school_id = str(getattr(school, "id", None)) if school else None
        log_exception_with_context(
            "workflow_engine: WorkflowRunLog create failed",
            school_id=school_id,
            extra={"error": str(e)},
        )
        logger.warning("WorkflowRunLog create failed: %s", e)
    try:
        from apps.schools.models import SchoolProvisioningEvent

        if school:
            SchoolProvisioningEvent.log_event(
                school=school,
                event_type="WORKFLOW_RUN",
                status="INFO",
                message=f"Workflow {template.code} ran; {len(actions_run)} action(s).",
                payload={
                    "template": template.code,
                    "actions_run": actions_run,
                    "context_keys": context_keys,
                },
            )
    except WORKFLOW_SOFT_FAILURES as e:
        school_id = str(getattr(school, "id", None)) if school else None
        log_exception_with_context(
            "workflow_engine: Workflow audit log failed",
            school_id=school_id,
            extra={"error": str(e)},
        )
        logger.warning("Workflow audit log failed: %s", e)

    # Section 11.4: Record workflow failure for customer success (health, auto-ticket)
    failed = [r for r in actions_run if isinstance(r, dict) and r.get("error")]
    if failed and school:
        try:
            from apps.customersuccess.services import record_workflow_failure

            error_summary = "; ".join([r.get("error", "")[:100] for r in failed[:3]])
            record_workflow_failure(
                school=school,
                workflow_name=getattr(template, "code", "")
                or str(getattr(template, "id", "")),
                workflow_run_id=audit_ref,
                error_summary=error_summary or "One or more actions failed",
                payload={"actions_run": actions_run},
            )
        except WORKFLOW_SOFT_FAILURES as e:
            school_id = str(getattr(school, "id", None)) if school else None
            log_exception_with_context(
                "workflow_engine: Workflow failure event record failed",
                school_id=school_id,
                extra={"error": str(e)},
            )
            logger.warning("Workflow failure event record failed: %s", e)

    return {
        "ok": True,
        "conditions_passed": True,
        "actions_run": actions_run,
        "audit_ref": audit_ref,
    }


def run_workflows_for_trigger(school, trigger_type: str, context: dict) -> list:
    """
    Run all active TenantWorkflows for this school whose template has the given trigger_type.
    Section 5: full execution engine entry point (scheduled, event, manual, webhook).
    Returns list of run_workflow result dicts.
    """
    from .models_workflow import TenantWorkflow

    qs = TenantWorkflow.objects.filter(
        school=school,
        is_active=True,
        template__is_active=True,
        template__trigger=trigger_type,
    ).select_related("template")
    results = []
    for tw in qs:
        try:
            r = run_workflow(tw, context)
            results.append(
                {"tenant_workflow_id": tw.pk, "template_code": tw.template.code, **r}
            )
        except WORKFLOW_SOFT_FAILURES as e:
            school_id = str(getattr(school, "id", None)) if school else None
            log_exception_with_context(
                "workflow_engine: run_workflow failed",
                school_id=school_id,
                extra={"tenant_workflow_id": tw.pk, "error": str(e)},
            )
            logger.warning("run_workflow failed: tw=%s error=%s", tw.pk, e)
            results.append(
                {
                    "tenant_workflow_id": tw.pk,
                    "template_code": getattr(tw.template, "code", ""),
                    "ok": False,
                    "error": str(e),
                }
            )
    return results
