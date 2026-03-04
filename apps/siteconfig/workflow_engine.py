"""
Minimal workflow execution engine (Part 2c). Evaluates conditions and runs actions; logs each run.
"""
import logging
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


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
        if op == "gt" and not (actual is not None and want is not None and actual > want):
            return False
        if op == "gte" and not (actual is not None and want is not None and actual >= want):
            return False
        if op == "lt" and not (actual is not None and want is not None and actual < want):
            return False
        if op == "lte" and not (actual is not None and want is not None and actual <= want):
            return False
        if op == "in" and actual not in (want if isinstance(want, (list, tuple)) else []):
            return False
    return True


def run_actions(actions: list, context: dict, school=None) -> list:
    """
    Run action list (e.g. [{"type": "notify", "params": {...}}]). Placeholder: only log.
    Returns list of results per action for audit.
    """
    results = []
    for a in actions or []:
        if not isinstance(a, dict):
            continue
        action_type = a.get("type", "")
        params = a.get("params") or {}
        # Placeholder: no side effects; just record that we would run this
        logger.info("Workflow action: type=%s params=%s school=%s", action_type, params, getattr(school, "id", None))
        results.append({"type": action_type, "params": params, "run_at": timezone.now().isoformat()})
    return results


def run_workflow(tenant_workflow, context: dict) -> dict:
    """
    Run a TenantWorkflow: merge template with overrides, evaluate conditions, run actions, log.
    Returns {"ok": bool, "conditions_passed": bool, "actions_run": list, "audit_ref": str}.
    """
    from .models_workflow import WorkflowTemplate, TenantWorkflow

    if not isinstance(tenant_workflow, TenantWorkflow):
        return {"ok": False, "error": "Invalid TenantWorkflow"}

    template = getattr(tenant_workflow, "template", None)
    if not template or not template.is_active:
        return {"ok": False, "error": "Template inactive or missing"}

    overrides = getattr(tenant_workflow, "overrides", None) or {}
    conditions = overrides.get("conditions", template.conditions) if isinstance(overrides.get("conditions"), list) else (template.conditions or [])
    actions = overrides.get("actions", template.actions) if isinstance(overrides.get("actions"), list) else (template.actions or [])

    conditions_passed = evaluate_conditions(conditions, context)
    if not conditions_passed:
        return {"ok": True, "conditions_passed": False, "actions_run": [], "audit_ref": ""}

    school = getattr(tenant_workflow, "school", None)
    actions_run = run_actions(actions, context, school=school)

    # Audit: log to compliance/SchoolProvisioningEvent or a dedicated WorkflowRunLog if added
    audit_ref = ""
    try:
        from apps.schools.models import SchoolProvisioningEvent
        if school:
            SchoolProvisioningEvent.log_event(
                school=school,
                event_type="WORKFLOW_RUN",
                status="INFO",
                message=f"Workflow {template.code} ran; {len(actions_run)} action(s).",
                payload={"template": template.code, "actions_run": actions_run, "context_keys": list(context.keys())},
            )
            audit_ref = "SchoolProvisioningEvent"
    except Exception as e:
        logger.warning("Workflow audit log failed: %s", e)

    return {
        "ok": True,
        "conditions_passed": True,
        "actions_run": actions_run,
        "audit_ref": audit_ref,
    }
