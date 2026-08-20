"""Pass/fail attention gateway for Workflow Flight Deck.

Successful runs leave the Action Required queue and land in a read-only
Success Logs history. Failed/stuck/running runs stay visible with a pipeline
train, live logs, and a step-specific remediator.
"""

from __future__ import annotations

from typing import Any

from django.utils.translation import gettext as _

SIMULATION_WORKFLOW_KEY = "workflow_flight_deck_simulation"

SIMULATION_STEPS: tuple[str, ...] = (
    "lint_verify",
    "build_package",
    "integration_test",
    "cloud_deploy",
)

SIMULATION_STEP_LABELS: dict[str, str] = {
    "lint_verify": "Lint & Verify",
    "build_package": "Build Package",
    "integration_test": "Integration Test",
    "cloud_deploy": "Cloud Deploy",
}

SIMULATION_FAIL_STEP = "integration_test"

SIMULATION_ERROR_TYPE = "PermissionError"
SIMULATION_ERROR_MESSAGE = (
    "AuthCheckSync service test runner cluster token expired"
)

SIMULATION_RUNBOOK_STEPS: tuple[str, ...] = (
    "Regenerate expired AuthCheckSync service test runner cluster token permissions.",
    "Confirm the runner cluster can reach the integration-test endpoint.",
    "Resume from Integration Test so Lint & Verify and Build Package are not replayed.",
)

SIMULATION_PRIMARY_ACTION = "Address & Patch Token Issue"

ACTION_REQUIRED_STATUSES = frozenset(
    {"running", "stuck", "failed", "cancelled", "degrading"}
)
SUCCESS_STATUSES = frozenset({"succeeded"})


def step_label(name: str) -> str:
    key = str(name or "").strip()
    if key in SIMULATION_STEP_LABELS:
        return SIMULATION_STEP_LABELS[key]
    return key.replace("_", " ").replace("-", " ").title() or _("Step")


def simulation_remediation() -> dict[str, Any]:
    return {
        "verdict": "match",
        "remediation_key": "authchecksync_cluster_token_expired",
        "human_action": SIMULATION_RUNBOOK_STEPS[0],
        "auto_fix_available": True,
        "auto_fix_kind": "resume_from_checkpoint",
        "primary_action_label": SIMULATION_PRIMARY_ACTION,
        "suggested_next": "Resume from the failed Integration Test step.",
        "runbook_steps": list(SIMULATION_RUNBOOK_STEPS),
        "failed_step": SIMULATION_FAIL_STEP,
        "failed_step_label": SIMULATION_STEP_LABELS[SIMULATION_FAIL_STEP],
        "source": "flight_deck_simulation",
    }


def bucket_for_run(run: Any) -> str:
    """Return action_required, success_logs, or hidden."""

    status = str(getattr(run, "status", "") or "").lower()
    try:
        from apps.platform_runtime.workflow_fix_handlers import workflow_run_is_remediated

        if workflow_run_is_remediated(run) and status not in SUCCESS_STATUSES:
            return "hidden"
    except Exception:
        pass
    if status in ACTION_REQUIRED_STATUSES:
        return "action_required"
    if status in SUCCESS_STATUSES:
        return "success_logs"
    return "hidden"


def pipeline_stages_for_run(run: Any) -> list[dict[str, Any]]:
    """Ordered visual train: done / running / failed / pending."""

    rows: list[dict[str, Any]] = []
    steps = []
    try:
        steps = list(run.steps.all().order_by("ordinal"))
    except Exception:
        steps = []
    run_status = str(getattr(run, "status", "") or "").lower()
    current_name = str(getattr(run, "current_step_name", "") or "")
    for step in steps:
        name = str(getattr(step, "name", "") or "")
        status = str(getattr(step, "status", "") or "pending").lower()
        visual = "pending"
        if status == "done":
            visual = "done"
        elif status == "failed" or (
            run_status in ("failed", "stuck") and name == current_name
        ):
            visual = "failed"
        elif status == "running" or (
            run_status in ("running", "degrading") and name == current_name
        ):
            visual = "running"
        rows.append(
            {
                "name": name,
                "label": getattr(step, "label", "") or step_label(name),
                "ordinal": int(getattr(step, "ordinal", 0) or 0),
                "status": status,
                "visual": visual,
            }
        )
    if rows:
        return rows
    key = str(getattr(run, "workflow_key", "") or "")
    definition_steps = ()
    try:
        from apps.platform_runtime.workflow_registry import WORKFLOWS

        definition = WORKFLOWS.get(key)
        if definition is not None:
            definition_steps = tuple(getattr(definition, "steps", ()) or ())
    except Exception:
        definition_steps = ()
    names = [getattr(item, "key", "") for item in definition_steps] or list(
        SIMULATION_STEPS if key == SIMULATION_WORKFLOW_KEY else ()
    )
    current = str(getattr(run, "current_step_name", "") or "")
    ordinal = int(getattr(run, "current_step_ordinal", 0) or 0)
    for index, name in enumerate(names, start=1):
        visual = "pending"
        if run_status in SUCCESS_STATUSES:
            visual = "done"
        elif name == current or index == ordinal:
            visual = "failed" if run_status in ("failed", "stuck") else "running"
        elif ordinal and index < ordinal:
            visual = "done"
        rows.append(
            {
                "name": name,
                "label": step_label(name),
                "ordinal": index,
                "status": visual,
                "visual": visual,
            }
        )
    return rows


def remediator_for_run(run: Any, *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    """Dynamic runbook pinned to the failed step."""

    data = payload or {}
    rem = dict(data.get("suggested_remediation") or getattr(run, "suggested_remediation", None) or {})
    status = str(data.get("status") or getattr(run, "status", "") or "").lower()
    if status not in ("failed", "stuck", "cancelled"):
        return {}
    stages = pipeline_stages_for_run(run)
    failed = next((row for row in stages if row.get("visual") == "failed"), None)
    failed_name = (
        rem.get("failed_step")
        or (failed or {}).get("name")
        or getattr(run, "current_step_name", "")
        or ""
    )
    failed_label = (
        rem.get("failed_step_label")
        or (failed or {}).get("label")
        or step_label(str(failed_name))
    )
    runbook = list(rem.get("runbook_steps") or [])
    if not runbook:
        human = str(rem.get("human_action") or "").strip()
        if human:
            runbook.append(human)
        next_hint = str(rem.get("suggested_next") or "").strip()
        if next_hint:
            runbook.append(next_hint)
        try:
            from apps.platform_runtime.workflow_recovery_playbook import (
                recovery_strategy_for_workflow,
            )

            strategy = recovery_strategy_for_workflow(
                str(getattr(run, "workflow_key", "") or data.get("workflow_key") or "")
            )
            summary = str(strategy.get("summary") or "").strip()
            if summary and summary not in runbook:
                runbook.append(summary)
        except Exception:
            pass
    if not runbook:
        runbook.append(
            _("Inspect the failed step, apply the suggested fix, then resume from that point.")
        )
    error = dict(data.get("error_summary") or getattr(run, "error_summary", None) or {})
    return {
        "title": _("Issue Remediator — Pipeline stuck at %(step)s")
        % {"step": failed_label},
        "failed_step": failed_name,
        "failed_step_label": failed_label,
        "runbook_steps": runbook[:8],
        "primary_action_label": rem.get("primary_action_label")
        or _("Resume from failure point"),
        "auto_fix_kind": rem.get("auto_fix_kind") or "",
        "auto_fix_available": bool(rem.get("auto_fix_available")),
        "error_type": error.get("type") or "",
        "error_message": error.get("message") or "",
    }


def attach_attention_fields(payload: dict[str, Any], *, run: Any | None = None) -> dict[str, Any]:
    """Add pipeline, remediator, and live log fields used by the Flight Deck UI."""

    out = dict(payload)
    if run is not None:
        out["pipeline"] = pipeline_stages_for_run(run)
        out["attention_bucket"] = bucket_for_run(run)
        remediator = remediator_for_run(run, payload=out)
        if remediator:
            out["remediator"] = remediator
            if remediator.get("primary_action_label"):
                for action in out.get("operator_actions") or []:
                    if action.get("kind") == "apply_fix" and remediator.get(
                        "auto_fix_available"
                    ):
                        action["label"] = remediator["primary_action_label"]
                        break
        logs = list(out.get("log_history") or [])
        if not logs:
            try:
                from apps.platform_runtime.workflow_telemetry import telemetry_from_payload

                logs = list(
                    telemetry_from_payload(getattr(run, "payload_summary", None)).get(
                        "log_history"
                    )
                    or []
                )
            except Exception:
                logs = []
        out["log_history"] = logs[-10:]
    else:
        out.setdefault("pipeline", [])
        out.setdefault("attention_bucket", "hidden")
        out.setdefault("log_history", list(out.get("log_history") or [])[-10:])
    return out


def compute_health(
    *,
    action_required: list[dict[str, Any]],
    success_logs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Operator metrics: workflow state, overall progress, health index."""

    failed = [
        row
        for row in action_required
        if str(row.get("status") or "") in ("failed", "cancelled")
    ]
    stuck = [row for row in action_required if str(row.get("status") or "") == "stuck"]
    running = [
        row
        for row in action_required
        if str(row.get("status") or "") in ("running", "degrading", "healing")
    ]
    featured = (failed or stuck or running or action_required or [None])[0]
    progress = 0
    if featured:
        try:
            progress = int(featured.get("progress_percent") or 0)
        except (TypeError, ValueError):
            progress = 0
    if failed or stuck:
        state = "Failed (Stuck)" if stuck else "Blocked"
        health = max(0, 75 - (8 * max(0, len(failed) - 1)) - (10 * len(stuck)))
    elif running:
        state = "Running"
        health = max(40, min(95, 60 + (progress // 4)))
    else:
        state = "Healthy"
        health = 100
        if success_logs:
            try:
                progress = int(success_logs[0].get("progress_percent") or 100)
            except (TypeError, ValueError):
                progress = 100
        else:
            progress = 100
    return {
        "workflow_state": state,
        "overall_progress": max(0, min(100, progress)),
        "health_index": max(0, min(100, health)),
        "featured_run_id": (featured or {}).get("id") if featured else None,
        "action_required_count": len(action_required),
        "success_count": len(success_logs),
    }


def list_success_logs(*, tenant_schema: str = "", limit: int = 20) -> list[Any]:
    from apps.platform_runtime.models import WorkflowRun

    qs = WorkflowRun.objects.filter(  # tenant-isolation-allow: operator-flight-deck-success-archive-optional-tenant-schema-filter
        status="succeeded"
    ).order_by("-ended_at", "-started_at")
    if tenant_schema:
        qs = qs.filter(tenant_schema=tenant_schema)
    return list(qs[:limit])
