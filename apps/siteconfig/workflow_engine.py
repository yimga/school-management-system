"""
Minimal workflow execution engine (Part 2c). Evaluates conditions and runs actions; logs each run.
School automation: SchoolAutomationWorkflow + simulation + extended actions.
"""

import json
import logging
from datetime import date, datetime, time
from smtplib import SMTPException
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date

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


def _context_get(context: dict, field: str):
    """Dot-path lookup for nested context (e.g. payload.amount)."""
    if not field or not isinstance(context, dict):
        return None
    cur = context
    for part in str(field).split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def _coerce_datetime(val):
    """Return timezone-aware datetime or None."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if timezone.is_aware(val) else timezone.make_aware(val)
    if isinstance(val, date) and not isinstance(val, datetime):
        return timezone.make_aware(datetime.combine(val, time.min))
    if isinstance(val, str):
        dt = parse_datetime(val)
        if dt:
            return dt if timezone.is_aware(dt) else timezone.make_aware(dt)
        donly = parse_date(val)
        if donly:
            return timezone.make_aware(datetime.combine(donly, time.min))
    return None


def expand_workflow_placeholders(obj, context: dict):
    """Resolve ${key} in strings and recurse dict/list (workflow authoring)."""
    import re

    ctx = context if isinstance(context, dict) else {}

    def _repl_string(s: str) -> str:
        def repl(m):
            key = m.group(1)
            v = _context_get(ctx, key) if "." in key else ctx.get(key)
            return "" if v is None else str(v)

        return re.sub(r"\$\{([^}]+)\}", repl, s)

    if isinstance(obj, str):
        return _repl_string(obj) if "${" in obj else obj
    if isinstance(obj, dict):
        return {k: expand_workflow_placeholders(v, ctx) for k, v in obj.items()}
    if isinstance(obj, list):
        return [expand_workflow_placeholders(x, ctx) for x in obj]
    return obj


def evaluate_conditions(conditions: list, context: dict) -> bool:
    """
    Evaluate a list of conditions against context. Each item: {"field": "...", "op": "eq"|"gt"|..., "value": ...}.
    Dot-path fields supported. Date/time ops: date_before, date_after, hour_between, weekday_in.
    Returns True if all conditions pass (or list is empty).
    """
    if not conditions:
        return True
    ctx = context if isinstance(context, dict) else {}
    for c in conditions:
        if not isinstance(c, dict):
            continue
        field = c.get("field", "")
        op = (c.get("op") or "eq").lower()
        want = c.get("value")
        actual = _context_get(ctx, field)
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
        if op == "date_before":
            a_dt = _coerce_datetime(actual)
            w_dt = _coerce_datetime(want)
            if not a_dt or not w_dt or not (a_dt.date() < w_dt.date()):
                return False
        elif op == "date_after":
            a_dt = _coerce_datetime(actual)
            w_dt = _coerce_datetime(want)
            if not a_dt or not w_dt or not (a_dt.date() > w_dt.date()):
                return False
        elif op == "date_on_or_before":
            a_dt = _coerce_datetime(actual)
            w_dt = _coerce_datetime(want)
            if not a_dt or not w_dt or not (a_dt.date() <= w_dt.date()):
                return False
        elif op == "date_on_or_after":
            a_dt = _coerce_datetime(actual)
            w_dt = _coerce_datetime(want)
            if not a_dt or not w_dt or not (a_dt.date() >= w_dt.date()):
                return False
        elif op == "hour_between":
            a_dt = _coerce_datetime(actual)
            if not a_dt or not isinstance(want, (list, tuple)) or len(want) != 2:
                return False
            try:
                h0, h1 = int(want[0]), int(want[1])
            except (TypeError, ValueError):
                return False
            h = a_dt.hour
            if h0 <= h1:
                ok = h0 <= h <= h1
            else:
                ok = h >= h0 or h <= h1
            if not ok:
                return False
        elif op == "weekday_in":
            a_dt = _coerce_datetime(actual)
            if not a_dt:
                return False
            wlist = want if isinstance(want, (list, tuple)) else []
            try:
                wd = [int(x) for x in wlist]
            except (TypeError, ValueError):
                return False
            if a_dt.weekday() not in wd:
                return False
        elif op == "role_in":
            want_list = want if isinstance(want, (list, tuple)) else []
            actual_role = (
                _context_get(ctx, field)
                if field
                else (
                    ctx.get("actor_role")
                    if isinstance(ctx, dict)
                    else None
                )
                or (ctx.get("trigger_role") if isinstance(ctx, dict) else None)
            )
            if actual_role not in want_list:
                return False
        elif op == "feature_enabled":
            key = str(want or field or "").strip()
            if not key:
                return False
            bucket = _context_get(ctx, "school_features")
            if not isinstance(bucket, dict):
                return False
            if not bucket.get(key):
                return False
    return True


def _run_action_notify(
    params: dict, context: dict, school=None, dry_run: bool = False, **kwargs
):
    """Send notification (email/push/in-app). params: channel, subject, body, recipient_ref (e.g. context key)."""
    if dry_run:
        return {
            "dry_run": True,
            "channel": params.get("channel") or "log",
            "preview": True,
        }
    channel = (params.get("channel") or "log").lower()
    if channel == "log":
        logger.info("Workflow notify: %s", params.get("body", params))
        return {}
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
    return {}


def _run_action_emit_event(
    params: dict, context: dict, school=None, dry_run: bool = False, **kwargs
):
    """Emit a domain event. params: event_type, payload (dict or context keys)."""
    if dry_run:
        return {"dry_run": True, "event_type": params.get("event_type")}
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
    return {}


def _run_action_webhook(
    params: dict, context: dict, school=None, dry_run: bool = False, **kwargs
):
    """POST JSON to external URL. params: url, payload (optional; defaults to context subset)."""
    url = expand_workflow_placeholders(params.get("url") or "", context)
    if not url:
        raise WorkflowActionExecutionError("webhook url missing")
    if dry_run:
        return {"dry_run": True, "would_post_url": url[:500]}
    raw_payload = params.get("payload")
    if raw_payload is None:
        body_obj = {k: v for k, v in (context or {}).items() if not str(k).startswith("_")}
    else:
        body_obj = expand_workflow_placeholders(raw_payload, context)
    data = json.dumps(body_obj, default=str).encode("utf-8")
    req = Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urlopen(req, timeout=min(int(params.get("timeout") or 15), 60)) as resp:
            return {"http_status": getattr(resp, "status", None) or 200}
    except (OSError, URLError, TimeoutError, ValueError) as e:
        raise WorkflowActionExecutionError(str(e)) from e


def _run_action_create_record(
    params: dict, context: dict, school=None, dry_run: bool = False, **kwargs
):
    """Persist SchoolWorkflowCreatedRecord (safe automation artifact)."""
    if not school:
        raise WorkflowActionExecutionError("school required")
    record_type = str(params.get("record_type") or "generic")[:80]
    payload = expand_workflow_placeholders(params.get("payload") or {}, context)
    if dry_run:
        return {"dry_run": True, "record_type": record_type, "payload_keys": list(payload.keys()) if isinstance(payload, dict) else []}
    from .models_workflow import SchoolWorkflowCreatedRecord

    wf_id = params.get("workflow_id") or (context or {}).get("_workflow_id")
    wf = None
    if wf_id:
        from .models_workflow import SchoolAutomationWorkflow

        try:
            wid = int(wf_id)
        except (TypeError, ValueError):
            wid = None
        if wid:
            wf = SchoolAutomationWorkflow.objects.filter(
                pk=wid, school_id=school.pk
            ).first()
    row = SchoolWorkflowCreatedRecord.objects.create(
        school=school,
        workflow=wf,
        record_type=record_type,
        payload=payload if isinstance(payload, dict) else {"data": payload},
    )
    return {"created_record_id": row.pk}


def _run_action_update_field(
    params: dict, context: dict, school=None, dry_run: bool = False, **kwargs
):
    """
    Limited updates: student_profile.custom_attributes merge when field=custom_attributes.
    object_id from params or context key object_context_key.
    """
    model_key = (params.get("model_key") or "").strip()
    merge = expand_workflow_placeholders(params.get("merge") or {}, context)
    if not isinstance(merge, dict):
        raise WorkflowActionExecutionError("merge must be an object")

    obj_key = params.get("object_context_key") or "student_id"
    oid = params.get("object_id")
    if oid is None:
        oid = _context_get(context, obj_key) if isinstance(context, dict) else None
    try:
        sid = int(oid)
    except (TypeError, ValueError):
        raise WorkflowActionExecutionError("object_id invalid") from None

    field = (params.get("field") or "custom_attributes").strip()
    if model_key != "student_profile" or field != "custom_attributes":
        raise WorkflowActionExecutionError("unsupported update_field target")

    if dry_run:
        return {"dry_run": True, "would_merge_custom_attributes": True, "student_id": sid}

    from apps.people.models import StudentProfile

    sp = StudentProfile.objects.filter(pk=sid, school=school).first()
    if not sp:
        raise WorkflowActionExecutionError("student_profile not found")
    cur = dict(sp.custom_attributes or {})
    cur.update(merge)
    sp.custom_attributes = cur
    sp.save(update_fields=["custom_attributes"])
    return {"updated": True, "student_id": sid}


def _run_action_delay(
    params: dict, context: dict, school=None, dry_run: bool = False, **kwargs
):
    """Pause execution for a bounded number of seconds (workflow automation)."""
    if dry_run:
        sec = min(max(int(params.get("seconds") or 0), 0), 300)
        return {"dry_run": True, "would_delay_seconds": sec}
    import time

    sec = max(0, min(int(params.get("seconds") or 0), 300))
    if sec:
        time.sleep(sec)
    return {"delayed_seconds": sec}


def _run_action_ai_suggestion(
    params: dict, context: dict, school=None, dry_run: bool = False, user=None, **kwargs
):
    """Draft AI text — uses workflow builder assistant when enabled; otherwise deterministic stub."""
    if dry_run:
        return {"dry_run": True, "ai_preview": True}
    intent = {
        "goal": str(params.get("goal") or "workflow automation hint"),
        "context_summary": str(params.get("context_summary") or "")[:300],
    }
    keys = params.get("include_context_keys") or []
    if isinstance(keys, (list, tuple)):
        for k in keys:
            if isinstance(k, str) and context and k in context:
                intent[k] = context[k]
    try:
        from apps.platform_runtime.ai_assistant_service import (
            draft_workflow_builder_assistant,
        )

        user_obj = user
        if user_obj is None:
            from django.contrib.auth import get_user_model

            User = get_user_model()
            user_obj = User.objects.filter(is_superuser=True).first()
        r = draft_workflow_builder_assistant(intent, school=school, user=user_obj)
        text = (r.get("draft_text") or "")[:4000]
        return {"suggestion_text": text, "requires_approval": True}
    except WORKFLOW_SOFT_FAILURES as e:
        logger.warning("ai_suggestion degraded: %s", e)
        return {
            "suggestion_text": "(AI suggestion unavailable in this environment.)",
            "requires_approval": True,
            "error": str(e),
        }


def run_actions(
    actions: list,
    context: dict,
    school=None,
    *,
    dry_run: bool = False,
    user=None,
) -> list:
    """
    Run action list (e.g. [{"type": "notify", "params": {...}}, {"type": "emit_event", "params": {...}}]).
    Supported types: notify, emit_event, webhook, create_record, update_field, ai_suggestion.
    Unknown types are logged only.
    Returns list of results per action for audit.
    24.13: Each action runs in try/except; a failed action records error in result
    and does not abort the rest of the workflow (safe degradation).
    """
    ACTION_HANDLERS = {
        "notify": _run_action_notify,
        "emit_event": _run_action_emit_event,
        "webhook": _run_action_webhook,
        "create_record": _run_action_create_record,
        "update_field": _run_action_update_field,
        "ai_suggestion": _run_action_ai_suggestion,
        "delay": _run_action_delay,
    }
    ALIAS_TYPES = {
        "send_message": "notify",
        "update_record": "update_field",
        "trigger_webhook": "webhook",
    }
    results = []
    for a in actions or []:
        if not isinstance(a, dict):
            continue
        action_type = (a.get("type") or "").strip()
        action_type = ALIAS_TYPES.get(action_type.lower(), action_type)
        params = a.get("params") or {}
        try:
            handler = ACTION_HANDLERS.get(action_type)
            extras = {}
            if handler:
                ret = handler(
                    params,
                    context,
                    school=school,
                    dry_run=dry_run,
                    user=user,
                )
                if isinstance(ret, dict):
                    extras = ret
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
                    "dry_run": dry_run,
                    **extras,
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
                    "dry_run": dry_run,
                    "error": str(e),
                }
            )
    return results


def _expected_output_from_planned(planned_actions: list) -> list[dict]:
    """Human-readable planned side effects for simulation UI and API."""
    out = []
    for p in planned_actions or []:
        if not isinstance(p, dict):
            continue
        t = p.get("type") or ""
        row: dict = {"action": t, "summary": ""}
        if t == "notify":
            ch = (p.get("params") or {}).get("channel") or p.get("channel") or "log"
            row["summary"] = f"Notification channel={ch} (preview)"
        elif t == "webhook":
            row["summary"] = p.get("would_post_url") or "POST webhook (preview)"
        elif t == "create_record":
            row["summary"] = f"Create record type={p.get('record_type', 'generic')}"
        elif t == "update_field":
            row["summary"] = "Merge custom_attributes on student (preview)"
        elif t == "ai_suggestion":
            row["summary"] = p.get("suggestion_text") or "AI draft (preview)"
        elif t == "emit_event":
            row["summary"] = f"Emit event (preview) type={p.get('event_type', '')}"
        elif t == "delay":
            row["summary"] = f"Delay (preview) seconds={p.get('delayed_seconds', p.get('would_delay_seconds', ''))}"
        else:
            row["summary"] = f"Run {t}"
        out.append(row)
    return out


def simulate_dsl(
    dsl: dict, context: dict, school=None, user=None
) -> dict:
    """
    Preview execution: conditions + dry-run actions (no external side effects beyond logging).
    """
    conditions = (dsl or {}).get("conditions") or []
    actions = (dsl or {}).get("actions") or []
    conditions_passed = evaluate_conditions(conditions, context)
    planned_actions = []
    if conditions_passed:
        planned_actions = run_actions(
            actions, context, school=school, dry_run=True, user=user
        )
    expected_output = _expected_output_from_planned(planned_actions)
    return {
        "conditions_passed": conditions_passed,
        "planned_actions": planned_actions,
        "expected_output": expected_output,
        "trigger": (dsl or {}).get("trigger"),
    }


def _validate_workflow_graph(graph: dict, dsl_trigger: str) -> list[str]:
    """When visual graph is present, require trigger → condition → action connectivity."""
    errs = []
    if not isinstance(graph, dict) or not graph:
        return errs
    nodes = graph.get("nodes")
    edges = graph.get("edges")
    if not isinstance(nodes, list) or not nodes:
        return errs
    kinds = set()
    node_ids = []
    for n in nodes:
        if not isinstance(n, dict):
            continue
        k = (n.get("kind") or "").strip()
        if k:
            kinds.add(k)
        nid = n.get("id")
        if nid:
            node_ids.append(str(nid))
    if "trigger" not in kinds:
        errs.append("visual graph must include a trigger node")
    if "condition" not in kinds:
        errs.append("visual graph must include at least one condition node")
    if "action" not in kinds:
        errs.append("visual graph must include at least one action node")
    trig = (dsl_trigger or "").strip()
    if trig and nodes:
        trigger_keys = [
            str(n.get("actionType") or n.get("nodeType") or "").strip()
            for n in nodes
            if isinstance(n, dict) and (n.get("kind") or "") == "trigger"
        ]
        if trigger_keys and trig not in trigger_keys:
            errs.append(
                "visual graph trigger node must match workflow trigger field (domain trigger)"
            )
    if isinstance(edges, list) and edges and node_ids:
        adj: dict[str, list[str]] = {nid: [] for nid in node_ids}
        for e in edges:
            if not isinstance(e, dict):
                continue
            f = e.get("from") or e.get("source")
            t = e.get("to") or e.get("target")
            if f is not None and t is not None:
                fs, ts = str(f), str(t)
                if fs in adj:
                    adj[fs].append(ts)
        trigger_ids = [
            str(n.get("id"))
            for n in nodes
            if isinstance(n, dict)
            and (n.get("kind") or "") == "trigger"
            and n.get("id")
        ]
        action_ids = {
            str(n.get("id"))
            for n in nodes
            if isinstance(n, dict) and (n.get("kind") or "") == "action" and n.get("id")
        }
        for start in trigger_ids:
            seen = {start}
            stack = [start]
            ok_action = False
            while stack:
                cur = stack.pop()
                if cur in action_ids:
                    ok_action = True
                    break
                for nxt in adj.get(cur, []):
                    if nxt not in seen:
                        seen.add(nxt)
                        stack.append(nxt)
            if not ok_action:
                errs.append(
                    "visual graph edges must connect trigger to at least one action"
                )
                break
    return errs


def validate_school_workflow_dsl(dsl: dict) -> list[str]:
    """Return human-readable errors; empty list means publish-safe."""
    errs = []
    if not isinstance(dsl, dict):
        return ["dsl must be an object"]
    trig = (dsl.get("trigger") or "").strip()
    if not trig:
        errs.append("trigger is required")
    for i, c in enumerate(dsl.get("conditions") or []):
        if not isinstance(c, dict):
            errs.append(f"conditions[{i}] must be an object")
            continue
        if not (c.get("field") or "").strip():
            errs.append(f"conditions[{i}].field is required")
        if not (c.get("op") or "").strip():
            errs.append(f"conditions[{i}].op is required")
    for i, a in enumerate(dsl.get("actions") or []):
        if not isinstance(a, dict):
            errs.append(f"actions[{i}] must be an object")
            continue
        if not (a.get("type") or "").strip():
            errs.append(f"actions[{i}].type is required")
    errs.extend(_validate_workflow_graph(dsl.get("graph") or {}, trig))
    return errs


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

    school = getattr(tenant_workflow, "school", None)
    if school is not None:
        try:
            from apps.platform_runtime.governor_limits import (
                record_workflow_run,
                workflow_run_limit_exceeded,
            )

            if workflow_run_limit_exceeded(school_id=getattr(school, "pk", None)):
                return {
                    "ok": False,
                    "error": "workflow_run_limit_exceeded",
                    "conditions_passed": False,
                    "actions_run": [],
                }
            record_workflow_run(school_id=getattr(school, "pk", None))
        except ImportError:
            pass

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


def sanitize_workflow_context_for_storage(context: dict | None) -> dict:
    """
    Persist a minimal, privacy-conscious context copy for action retries
    (IDs, amounts, short strings; truncates long values).
    """
    if not isinstance(context, dict):
        return {}
    out: dict = {}
    for k, v in context.items():
        ks = str(k)
        if ks.startswith("_"):
            continue
        if isinstance(v, (int, float, bool)) or v is None:
            out[ks] = v
        elif isinstance(v, str):
            out[ks] = v[:500] + ("…" if len(v) > 500 else "")
        else:
            try:
                s = json.dumps(v, default=str)
            except TypeError:
                s = str(v)
            out[ks] = s[:500] + ("…" if len(s) > 500 else "")
    return out


def retry_failed_actions_from_log(
    execution_log_id: int,
    *,
    user=None,
    context_override: dict | None = None,
) -> dict:
    """
    Re-run only actions that recorded an error on this execution log.
    Uses context_snapshot from the log merged with context_override.
    """
    from .models_workflow import SchoolWorkflowExecutionLog

    log = (
        SchoolWorkflowExecutionLog.objects.select_related("workflow", "workflow__school")
        .filter(pk=execution_log_id)
        .first()
    )
    if not log:
        return {"ok": False, "error": "execution_log_not_found"}
    wf = log.workflow
    school = wf.school

    actions_run = list(log.actions_run or [])
    failed_indices = [
        i
        for i, r in enumerate(actions_run)
        if isinstance(r, dict) and r.get("error")
    ]
    if not failed_indices:
        return {
            "ok": True,
            "retried": 0,
            "actions_run": actions_run,
            "audit_ref": str(log.pk),
            "message": "no_failed_actions",
        }

    dsl = get_school_workflow_dsl(wf)
    full_actions = dsl.get("actions") or []
    ctx = dict(log.context_snapshot or {})
    if isinstance(context_override, dict):
        ctx.update(context_override)
    ctx["_workflow_id"] = wf.pk

    retried = 0
    for i in failed_indices:
        if i >= len(full_actions):
            continue
        act = full_actions[i]
        if not isinstance(act, dict):
            continue
        single_results = run_actions([act], ctx, school=school, user=user)
        if single_results:
            actions_run[i] = single_results[0]
            retried += 1

    still_failed = [
        r for r in actions_run if isinstance(r, dict) and r.get("error")
    ]
    try:
        log.actions_run = actions_run
        log.retry_count = (log.retry_count or 0) + 1
        log.run_status = (
            SchoolWorkflowExecutionLog.RunStatus.FAILED
            if still_failed
            else SchoolWorkflowExecutionLog.RunStatus.SUCCESS
        )
        log.error_message = (
            still_failed[0].get("error", "")[:2000] if still_failed else ""
        )
        log.save(
            update_fields=["actions_run", "retry_count", "run_status", "error_message"]
        )
    except WORKFLOW_SOFT_FAILURES as e:
        logger.warning("retry_failed_actions_from_log save failed: %s", e)
        return {"ok": False, "error": str(e)}

    return {
        "ok": True,
        "retried": retried,
        "actions_run": actions_run,
        "audit_ref": str(log.pk),
        "run_status": log.run_status,
    }


def get_school_workflow_dsl(school_workflow) -> dict:
    """Effective DSL for a school-authored automation workflow."""
    from .models_workflow import SchoolAutomationWorkflow

    if not isinstance(school_workflow, SchoolAutomationWorkflow):
        return {}
    return {
        "trigger": school_workflow.trigger,
        "trigger_config": school_workflow.trigger_config or {},
        "conditions": list(school_workflow.conditions or []),
        "actions": list(school_workflow.actions or []),
        "graph": school_workflow.graph or {},
    }


def run_school_workflow(school_workflow, context: dict, *, user=None) -> dict:
    """
    Execute a published SchoolAutomationWorkflow (conditions → actions → execution log).
    """
    from .models_workflow import SchoolAutomationWorkflow, SchoolWorkflowExecutionLog

    if not isinstance(school_workflow, SchoolAutomationWorkflow):
        return {"ok": False, "error": "Invalid SchoolAutomationWorkflow"}

    if school_workflow.status != SchoolAutomationWorkflow.Status.PUBLISHED:
        return {"ok": False, "error": "Workflow is not published"}
    if not school_workflow.is_active:
        return {"ok": False, "error": "Workflow is inactive"}

    school = school_workflow.school
    dsl = get_school_workflow_dsl(school_workflow)
    conditions = dsl.get("conditions") or []
    actions = dsl.get("actions") or []

    ctx = dict(context) if isinstance(context, dict) else {}
    ctx["_workflow_id"] = school_workflow.pk

    conditions_passed = evaluate_conditions(conditions, ctx)
    safe_keys = sorted([k for k in ctx.keys() if not str(k).startswith("_")])

    if not conditions_passed:
        audit_ref = ""
        try:
            log = SchoolWorkflowExecutionLog.objects.create(
                workflow=school_workflow,
                conditions_passed=False,
                actions_run=[],
                context_keys=safe_keys,
                context_snapshot={},
                run_status=SchoolWorkflowExecutionLog.RunStatus.SKIPPED,
            )
            audit_ref = str(log.pk)
        except WORKFLOW_SOFT_FAILURES as e:
            logger.warning("SchoolWorkflowExecutionLog create failed: %s", e)
        return {
            "ok": True,
            "conditions_passed": False,
            "actions_run": [],
            "audit_ref": audit_ref,
            "school_workflow_id": school_workflow.pk,
        }

    actions_run = run_actions(actions, ctx, school=school, user=user)
    failed = [r for r in actions_run if isinstance(r, dict) and r.get("error")]
    try:
        from apps.platform_runtime.governor_limits import record_workflow_run

        record_workflow_run(school_id=getattr(school, "id", None))
    except WORKFLOW_SOFT_FAILURES:
        pass

    audit_ref = ""
    try:
        log = SchoolWorkflowExecutionLog.objects.create(
            workflow=school_workflow,
            conditions_passed=True,
            actions_run=actions_run,
            context_keys=safe_keys,
            context_snapshot=sanitize_workflow_context_for_storage(ctx),
            run_status=(
                SchoolWorkflowExecutionLog.RunStatus.FAILED
                if failed
                else SchoolWorkflowExecutionLog.RunStatus.SUCCESS
            ),
            error_message=(failed[0].get("error", "")[:2000] if failed else ""),
        )
        audit_ref = str(log.pk)
    except WORKFLOW_SOFT_FAILURES as e:
        logger.warning("SchoolWorkflowExecutionLog create failed: %s", e)

    return {
        "ok": True,
        "conditions_passed": True,
        "actions_run": actions_run,
        "audit_ref": audit_ref,
        "school_workflow_id": school_workflow.pk,
    }


def run_school_workflows_for_trigger(school, trigger_type: str, context: dict) -> list:
    """Run all published active school automation workflows for trigger_type."""
    from .models_workflow import SchoolAutomationWorkflow

    qs = SchoolAutomationWorkflow.objects.filter(
        school=school,
        is_active=True,
        status=SchoolAutomationWorkflow.Status.PUBLISHED,
        trigger=trigger_type,
    ).only(
        "pk",
        "school_id",
        "trigger",
        "trigger_config",
        "conditions",
        "actions",
        "graph",
        "is_active",
        "status",
    )
    results = []
    for wf in qs:
        try:
            r = run_school_workflow(wf, context)
            results.append({"school_workflow_id": wf.pk, **r})
        except WORKFLOW_SOFT_FAILURES as e:
            school_id = str(getattr(school, "id", None)) if school else None
            log_exception_with_context(
                "workflow_engine: run_school_workflow failed",
                school_id=school_id,
                extra={"school_workflow_id": wf.pk, "error": str(e)},
            )
            logger.warning("run_school_workflow failed: wf=%s error=%s", wf.pk, e)
            results.append(
                {
                    "school_workflow_id": wf.pk,
                    "ok": False,
                    "error": str(e),
                }
            )
    return results


def dispatch_domain_triggers(school, trigger_type: str, context: dict) -> dict:
    """Run catalog tenant workflows and school automation workflows for one trigger."""
    tenant = run_workflows_for_trigger(school, trigger_type, context)
    school_wf = run_school_workflows_for_trigger(school, trigger_type, context)
    visual = []
    try:
        from apps.automation.visual_executor import run_matching_visual_workflows

        visual = run_matching_visual_workflows(school, trigger_type, context)
    except WORKFLOW_SOFT_FAILURES:
        visual = []
    return {
        "tenant_workflows": tenant,
        "school_workflows": school_wf,
        "visual_workflows": visual,
    }
