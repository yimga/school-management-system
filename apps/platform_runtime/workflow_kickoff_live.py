"""Kickoff-page live attention for every workflow engine.

Flight Deck (progress bus) and Migration Cloud already isolate fail vs success.
This module is the shared contract the other engines call: latest state only,
so a later success cannot keep an old failure in Action Required.

Engines:
  A. Progress bus — ``WorkflowRun`` via ``bucket_for_run``
  B. Automation — latest ``SchoolWorkflowExecutionLog`` per workflow
  C. Orchestration — latest ``OrchestrationRun`` per process definition
  D. Approvals — pending ``AutomationApprovalQueue`` rows only
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _

from apps.platform_runtime.workflow_attention_gateway import (
    ACTION_REQUIRED_STATUSES,
    SIMULATION_WORKFLOW_KEY,
    SUCCESS_STATUSES,
    attach_attention_fields,
    bucket_for_run,
    remediator_for_run,
    step_label,
)

TENANT_HIDDEN_WORKFLOW_KEYS = frozenset({SIMULATION_WORKFLOW_KEY})

ORCHESTRATION_FAILED = frozenset({"failed", "compensating"})
ORCHESTRATION_IN_FLIGHT = frozenset({"pending", "running", "compensating"})
AUTOMATION_FAILED = frozenset({"failed"})
AUTOMATION_IN_FLIGHT = frozenset({"pending"})
_COMPLETE_PERCENT = 100  # magic-number-allow: percent-complete-ceiling


def _school_id(school: Any | None) -> str:
    if school is None:
        return ""
    return str(getattr(school, "pk", "") or getattr(school, "id", "") or "")


def _tenant_schema(school: Any | None, *, fallback: str = "") -> str:
    if school is None:
        return fallback
    return str(getattr(school, "schema_name", "") or fallback or "")


def _progress_bus_queryset(*, tenant_schema: str = "", school_id: str = "", control_plane: bool = False):
    try:
        from apps.platform_runtime.models import WorkflowRun
    except Exception:
        return None
    # tenant-isolation-allow: kickoff-live-progress-bus-optional-tenant-filter
    qs = WorkflowRun.objects.all()
    if tenant_schema:
        qs = qs.filter(tenant_schema=tenant_schema)
    if school_id:
        qs = qs.filter(school_id=str(school_id))
    if not control_plane:
        qs = qs.exclude(workflow_key__in=TENANT_HIDDEN_WORKFLOW_KEYS)
    return qs


def latest_progress_run(
    workflow_key: str,
    *,
    tenant_schema: str = "",
    school_id: str = "",
    control_plane: bool = False,
) -> Any | None:
    """Newest ``WorkflowRun`` for one registry key, tenant-scoped when given."""

    key = str(workflow_key or "").strip()
    if not key:
        return None
    if not control_plane and key in TENANT_HIDDEN_WORKFLOW_KEYS:
        return None
    qs = _progress_bus_queryset(
        tenant_schema=tenant_schema,
        school_id=school_id,
        control_plane=control_plane,
    )
    if qs is None:
        return None
    return qs.filter(workflow_key=key).order_by("-started_at", "-id").first()


def compose_from_progress_run(run: Any | None) -> dict[str, Any]:
    """JSON-safe kickoff board for one progress-bus run."""

    empty = {
        "engine": "progress_bus",
        "percent": 0,
        "processed": 0,
        "expected": 0,
        "in_flight": False,
        "issues_open": 0,
        "needs_attention": False,
        "attention_bucket": "hidden",
        "pipeline": [],
        "remediator": None,
        "run_id": None,
        "workflow_key": "",
        "status": "",
    }
    if run is None:
        return empty
    try:
        from apps.platform_runtime.workflow_tracker import serialize_workflow_run

        payload = serialize_workflow_run(run)
    except Exception:
        payload = {
            "id": getattr(run, "pk", None),
            "workflow_key": getattr(run, "workflow_key", "") or "",
            "status": str(getattr(run, "status", "") or ""),
            "progress_percent": 0,
            "records_processed": 0,
            "records_expected": 0,
        }
    attached = attach_attention_fields(payload, run=run)
    bucket = str(attached.get("attention_bucket") or bucket_for_run(run) or "hidden")
    status = str(attached.get("status") or getattr(run, "status", "") or "").lower()
    in_flight = status in {"running", "degrading", "healing"}
    issues = 1 if bucket == "action_required" and status in (
        "failed",
        "stuck",
        "cancelled",
        "degrading",
    ) else 0
    remediator = attached.get("remediator") or remediator_for_run(run, payload=attached)
    if not issues:
        remediator = None
    percent = int(attached.get("progress_percent") or 0)
    if status in SUCCESS_STATUSES:
        percent = _COMPLETE_PERCENT
        issues = 0
        remediator = None
    return {
        "engine": "progress_bus",
        "percent": percent,
        "processed": int(attached.get("records_processed") or 0),
        "expected": int(attached.get("records_expected") or 0),
        "in_flight": in_flight,
        "issues_open": issues,
        "needs_attention": bool(issues),
        "attention_bucket": bucket,
        "pipeline": list(attached.get("pipeline") or []),
        "remediator": remediator or None,
        "run_id": attached.get("id") or getattr(run, "pk", None),
        "workflow_key": attached.get("workflow_key") or "",
        "status": status,
        "apply_fix_kind": (remediator or {}).get("auto_fix_kind") or "",
    }


def _orchestration_pipeline(run: Any) -> list[dict[str, Any]]:
    status = str(getattr(run, "status", "") or "").lower()
    names = ("queue", "execute", "compensate", "complete")
    visual_map = {
        "pending": ("running", "pending", "pending", "pending"),
        "running": ("done", "running", "pending", "pending"),
        "compensating": ("done", "done", "running", "pending"),
        "failed": ("done", "failed", "pending", "pending"),
        "completed": ("done", "done", "done", "done"),
        "cancelled": ("done", "failed", "pending", "pending"),
    }
    visuals = visual_map.get(status, ("pending", "pending", "pending", "pending"))
    rows = []
    for index, name in enumerate(names):
        rows.append(
            {
                "name": name,
                "key": name,
                "label": step_label(name),
                "ordinal": index + 1,
                "status": visuals[index],
                "visual": visuals[index],
            }
        )
    return rows


def compose_from_orchestration_run(run: Any | None) -> dict[str, Any]:
    """Kickoff board for one long-running process instance."""

    empty = {
        "engine": "orchestration",
        "percent": 0,
        "processed": 0,
        "expected": 0,
        "in_flight": False,
        "issues_open": 0,
        "needs_attention": False,
        "attention_bucket": "hidden",
        "pipeline": [],
        "remediator": None,
        "run_id": None,
        "workflow_key": "",
        "status": "",
    }
    if run is None:
        return empty
    status = str(getattr(run, "status", "") or "").lower()
    in_flight = status in ORCHESTRATION_IN_FLIGHT
    failed = status in ORCHESTRATION_FAILED
    overdue = bool(getattr(run, "sla_overdue", False))
    issues = 1 if failed or overdue else 0
    percent = 0
    if status == "pending":
        percent = 5
    elif status == "running":
        percent = 45
    elif status == "compensating":
        percent = 70
    elif status == "completed":
        percent = _COMPLETE_PERCENT
        issues = 0
    elif status in {"failed", "cancelled"}:
        percent = 40
    remediator = None
    if issues:
        err = str(getattr(run, "error_message", "") or "").strip()
        code = ""
        try:
            code = str(getattr(run.definition, "code", "") or "")
        except Exception:
            code = ""
        remediator = {
            "title": _("Issue Remediator — %(code)s stuck") % {"code": code or _("process")},
            "failed_step": "execute" if failed else "queue",
            "failed_step_label": step_label("execute" if failed else "queue"),
            "runbook_steps": [
                err or _("Inspect the failed step, then retry this run from the workbench."),
                _("A later successful run of the same process clears this alert."),
            ],
            "primary_action_label": _("Retry from failure point"),
            "auto_fix_kind": "",
            "auto_fix_available": False,
            "error_type": "OrchestrationRunFailed" if failed else "SlaOverdue",
            "error_message": err,
        }
    bucket = "action_required" if issues or in_flight else (
        "success_logs" if status == "completed" else "hidden"
    )
    return {
        "engine": "orchestration",
        "percent": percent,
        "processed": 1 if status == "completed" else 0,
        "expected": 1,
        "in_flight": in_flight and not failed,
        "issues_open": issues,
        "needs_attention": bool(issues),
        "attention_bucket": bucket,
        "pipeline": _orchestration_pipeline(run),
        "remediator": remediator,
        "run_id": getattr(run, "pk", None),
        "workflow_key": str(getattr(getattr(run, "definition", None), "code", "") or ""),
        "status": status,
        "apply_fix_kind": "",
    }


def compose_from_automation_log(log: Any | None) -> dict[str, Any]:
    """Kickoff board for the latest school-automation execution."""

    empty = {
        "engine": "automation",
        "percent": 0,
        "processed": 0,
        "expected": 0,
        "in_flight": False,
        "issues_open": 0,
        "needs_attention": False,
        "attention_bucket": "hidden",
        "pipeline": [],
        "remediator": None,
        "run_id": None,
        "workflow_key": "",
        "status": "",
    }
    if log is None:
        return empty
    status = str(getattr(log, "run_status", "") or "").lower()
    failed = status in AUTOMATION_FAILED
    in_flight = status in AUTOMATION_IN_FLIGHT
    issues = 1 if failed else 0
    names = ("evaluate", "act", "audit")
    if status in {"success", "skipped"}:
        visuals = ("done", "done", "done")
        percent = _COMPLETE_PERCENT
    elif failed:
        visuals = ("done", "failed", "pending")
        percent = 50
    else:
        visuals = ("running", "pending", "pending")
        percent = 15
    pipeline = [
        {
            "name": name,
            "key": name,
            "label": step_label(name),
            "ordinal": index + 1,
            "status": visuals[index],
            "visual": visuals[index],
        }
        for index, name in enumerate(names)
    ]
    remediator = None
    if issues:
        err = str(getattr(log, "error_message", "") or "").strip()
        remediator = {
            "title": _("Issue Remediator — automation action failed"),
            "failed_step": "act",
            "failed_step_label": step_label("act"),
            "runbook_steps": [
                err or _("Retry the failed actions from the automation builder."),
                _("A later successful run of this workflow clears this alert."),
            ],
            "primary_action_label": _("Retry failed actions"),
            "auto_fix_kind": "",
            "auto_fix_available": False,
            "error_type": "SchoolWorkflowFailed",
            "error_message": err,
        }
    return {
        "engine": "automation",
        "percent": percent,
        "processed": 1 if status in {"success", "skipped"} else 0,
        "expected": 1,
        "in_flight": in_flight,
        "issues_open": issues,
        "needs_attention": bool(issues),
        "attention_bucket": "action_required" if issues else (
            "success_logs" if status in {"success", "skipped"} else "hidden"
        ),
        "pipeline": pipeline,
        "remediator": remediator,
        "run_id": getattr(log, "pk", None),
        "workflow_key": str(getattr(getattr(log, "workflow", None), "trigger", "") or ""),
        "status": status,
        "apply_fix_kind": "",
    }


def latest_orchestration_runs(*, school: Any | None = None) -> list[Any]:
    """Newest run per process definition (school-scoped when given)."""

    try:
        from apps.orchestration.models import OrchestrationRun
    except Exception:
        return []
    # tenant-isolation-allow: kickoff-live-orchestration-latest-per-definition-optional-school-fk
    qs = OrchestrationRun.objects.select_related("definition").order_by("-created_at")
    if school is not None:
        qs = qs.filter(school=school)
    seen: dict[Any, Any] = {}
    for run in qs[:80]:
        key = (getattr(run, "school_id", None), getattr(run, "definition_id", None))
        if key not in seen:
            seen[key] = run
    return list(seen.values())


def open_orchestration_failure_count(*, school: Any | None = None) -> int:
    """Count definitions whose *current* run is still failed — not all-time."""

    n = 0
    for run in latest_orchestration_runs(school=school):
        status = str(getattr(run, "status", "") or "").lower()
        if status in ORCHESTRATION_FAILED or bool(getattr(run, "sla_overdue", False)):
            n += 1
    return n


def latest_automation_logs(*, school: Any | None = None) -> list[Any]:
    """Newest execution log per school automation workflow."""

    try:
        from apps.siteconfig.models_workflow import SchoolWorkflowExecutionLog
    except Exception:
        return []
    qs = SchoolWorkflowExecutionLog.objects.select_related("workflow").order_by(
        "-created_at"
    )
    if school is not None:
        qs = qs.filter(workflow__school=school)
    seen: dict[Any, Any] = {}
    for log in qs[:80]:
        key = getattr(log, "workflow_id", None)
        if key not in seen:
            seen[key] = log
    return list(seen.values())


def open_automation_failure_count(*, school: Any | None = None) -> int:
    """Count automations whose *current* execution is still failed."""

    n = 0
    for log in latest_automation_logs(school=school):
        if str(getattr(log, "run_status", "") or "").lower() in AUTOMATION_FAILED:
            n += 1
    return n


def latest_progress_runs(
    *,
    tenant_schema: str = "",
    school_id: str = "",
    limit: int = 80,
    control_plane: bool = False,
) -> list[Any]:
    """Newest progress-bus run per workflow_key."""

    qs = _progress_bus_queryset(
        tenant_schema=tenant_schema,
        school_id=school_id,
        control_plane=control_plane,
    )
    if qs is None:
        return []
    seen: dict[str, Any] = {}
    for run in qs.order_by("-started_at", "-id")[: max(limit * 4, limit)]:
        key = str(getattr(run, "workflow_key", "") or "")
        if key and key not in seen:
            seen[key] = run
        if len(seen) >= limit:
            break
    return list(seen.values())


def open_progress_bus_failure_count(
    *,
    tenant_schema: str = "",
    school_id: str = "",
    control_plane: bool = False,
) -> int:
    n = 0
    for run in latest_progress_runs(
        tenant_schema=tenant_schema,
        school_id=school_id,
        control_plane=control_plane,
    ):
        bucket = bucket_for_run(run)
        status = str(getattr(run, "status", "") or "").lower()
        if bucket == "action_required" and status in ACTION_REQUIRED_STATUSES - {
            "running"
        }:
            n += 1
    return n


def pending_approval_count(*, school: Any | None = None) -> int:
    try:
        from apps.automation.models import AutomationApprovalQueue
    except Exception:
        return 0
    # tenant-isolation-allow: kickoff-live-approval-queue-pending-optional-school-fk
    qs = AutomationApprovalQueue.objects.filter(
        status=AutomationApprovalQueue.Status.PENDING,
    )
    if school is not None and getattr(school, "pk", None):
        qs = qs.filter(school=school)
    try:
        return int(qs.count())
    except Exception:
        return 0


def compose_engine_attention(
    school: Any | None = None,
    *,
    tenant_schema: str = "",
    school_id: str = "",
    control_plane: bool = False,
) -> dict[str, Any]:
    """Cross-engine Action Required counts from *current* state only."""

    sid = school_id or _school_id(school)
    schema = tenant_schema or _tenant_schema(school)
    orch = open_orchestration_failure_count(school=school)
    auto = open_automation_failure_count(school=school)
    bus = open_progress_bus_failure_count(
        tenant_schema=schema,
        school_id=sid,
        control_plane=control_plane,
    )
    approvals = pending_approval_count(school=school)
    issues = orch + auto + bus + approvals
    remediator = None
    if issues:
        steps = []
        if orch:
            steps.append(
                _("Retry the open orchestration process — completed retries clear this count.")
            )
        if auto:
            steps.append(
                _("Retry failed automation actions — a later success hides the alert.")
            )
        if bus:
            steps.append(_("Open the Flight Deck remediator for the failed platform job."))
        if approvals:
            steps.append(_("Clear pending approvals in the Approval Hub."))
        remediator = {
            "title": _("Issue Remediator — %(n)s open workflow issue(s)")
            % {"n": issues},
            "failed_step": "execute",
            "failed_step_label": _("Open issues"),
            "runbook_steps": steps[:8],
            "primary_action_label": _("Review open issues"),
            "auto_fix_kind": "",
            "auto_fix_available": False,
            "error_type": "",
            "error_message": "",
        }
    in_flight = False
    for run in latest_progress_runs(
        tenant_schema=schema,
        school_id=sid,
        limit=20,
        control_plane=control_plane,
    ):
        if str(getattr(run, "status", "") or "").lower() in {"running", "degrading"}:
            in_flight = True
            break
    if not in_flight:
        for run in latest_orchestration_runs(school=school):
            if str(getattr(run, "status", "") or "").lower() in ORCHESTRATION_IN_FLIGHT:
                in_flight = True
                break
    return {
        "engine": "all",
        "percent": _COMPLETE_PERCENT if issues == 0 and not in_flight else (35 if issues else 60),
        "processed": 0,
        "expected": 0,
        "in_flight": in_flight,
        "issues_open": issues,
        "needs_attention": bool(issues),
        "attention_bucket": "action_required" if issues else "success_logs",
        "pipeline": [],
        "remediator": remediator,
        "run_id": None,
        "workflow_key": "",
        "status": "blocked" if issues else ("running" if in_flight else "healthy"),
        "apply_fix_kind": "",
        "orchestration_open": orch,
        "automation_open": auto,
        "progress_bus_open": bus,
        "approvals_pending": approvals,
    }


def latest_orchestration_for_code(code: str, *, school: Any | None = None) -> Any | None:
    needle = str(code or "").strip()
    if not needle:
        return None
    try:
        from apps.orchestration.models import OrchestrationRun
    except Exception:
        return None
    qs = OrchestrationRun.objects.select_related("definition").filter(
        definition__code=needle
    )
    if school is not None:
        qs = qs.filter(school=school)
    return qs.order_by("-created_at").first()


def latest_automation_for_trigger(trigger: str, *, school: Any | None = None) -> Any | None:
    needle = str(trigger or "").strip()
    if not needle:
        return None
    try:
        from apps.siteconfig.models_workflow import SchoolWorkflowExecutionLog
    except Exception:
        return None
    qs = SchoolWorkflowExecutionLog.objects.select_related("workflow").filter(
        workflow__trigger=needle
    )
    if school is not None:
        qs = qs.filter(workflow__school=school)
    return qs.order_by("-created_at").first()


def compose_kickoff_live(
    *,
    workflow_key: str = "",
    school: Any | None = None,
    tenant_schema: str = "",
    school_id: str = "",
    attention: bool = False,
    control_plane: bool = False,
) -> dict[str, Any]:
    """Resolve the best live board for a kickoff page.

    Prefer the progress bus when a ``WorkflowRun`` exists for the key; otherwise
    fall through to orchestration (process code) then automation (trigger).
    ``attention=True`` (or empty key) returns the cross-engine summary.
    """

    sid = school_id or _school_id(school)
    schema = tenant_schema or _tenant_schema(school)
    key = str(workflow_key or "").strip()
    if attention or not key:
        payload = compose_engine_attention(
            school,
            tenant_schema=schema,
            school_id=sid,
            control_plane=control_plane,
        )
        payload["workflow_key"] = key
        return payload

    run = latest_progress_run(
        key,
        tenant_schema=schema,
        school_id=sid,
        control_plane=control_plane,
    )
    if run is not None:
        return compose_from_progress_run(run)

    orch = latest_orchestration_for_code(key, school=school)
    if orch is not None:
        return compose_from_orchestration_run(orch)

    auto = latest_automation_for_trigger(key, school=school)
    if auto is not None:
        return compose_from_automation_log(auto)

    idle = compose_from_progress_run(None)
    idle["workflow_key"] = key
    return idle


def mark_orchestration_open_failures(
    runs: list[Any], *, school: Any | None = None
) -> list[Any]:
    """Annotate a workbench list: only the current failed run per school+definition is open."""

    open_ids = set()
    for current in latest_orchestration_runs(school=school):
        status = str(getattr(current, "status", "") or "").lower()
        if status in ORCHESTRATION_FAILED or bool(getattr(current, "sla_overdue", False)):
            open_ids.add(getattr(current, "pk", None))
    for run in runs:
        pk = getattr(run, "pk", None)
        status = str(getattr(run, "status", "") or "").lower()
        setattr(run, "open_failure", pk in open_ids)
        setattr(
            run,
            "superseded_failure",
            status in ORCHESTRATION_FAILED and pk not in open_ids,
        )
    return runs
