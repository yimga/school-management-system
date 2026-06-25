"""Shared workflow status taxonomy for operator UI, APIs, and copilot context."""

from __future__ import annotations

from typing import Any


WORKFLOW_STATUS_TAXONOMY: dict[str, dict[str, str]] = {
    "running": {
        "key": "running",
        "label": "Running",
        "tone": "info",
        "color": "blue",
        "css_class": "rmc-wf-status--running",
    },
    "waiting": {
        "key": "waiting",
        "label": "Waiting",
        "tone": "muted",
        "color": "slate",
        "css_class": "rmc-wf-status--waiting",
    },
    "degrading": {
        "key": "degrading",
        "label": "Degrading",
        "tone": "warning",
        "color": "amber",
        "css_class": "rmc-wf-status--degrading",
    },
    "stuck": {
        "key": "stuck",
        "label": "Stuck",
        "tone": "stuck",
        "color": "yellow",
        "css_class": "rmc-wf-status--stuck",
    },
    "failed": {
        "key": "failed",
        "label": "Failed",
        "tone": "danger",
        "color": "red",
        "css_class": "rmc-wf-status--failed",
    },
    "cancelled": {
        "key": "cancelled",
        "label": "Stopped",
        "tone": "danger",
        "color": "red",
        "css_class": "rmc-wf-status--cancelled",
    },
    "stopped": {
        "key": "stopped",
        "label": "Stopped",
        "tone": "danger",
        "color": "red",
        "css_class": "rmc-wf-status--stopped",
    },
    "healing": {
        "key": "healing",
        "label": "Healing",
        "tone": "healing",
        "color": "teal",
        "css_class": "rmc-wf-status--healing",
    },
    "remediating": {
        "key": "remediating",
        "label": "Healing",
        "tone": "healing",
        "color": "teal",
        "css_class": "rmc-wf-status--healing",
    },
    "succeeded": {
        "key": "succeeded",
        "label": "Passed",
        "tone": "success",
        "color": "green",
        "css_class": "rmc-wf-status--succeeded",
    },
    "passed": {
        "key": "passed",
        "label": "Passed",
        "tone": "success",
        "color": "green",
        "css_class": "rmc-wf-status--succeeded",
    },
    "superseded": {
        "key": "superseded",
        "label": "Superseded",
        "tone": "resolved",
        "color": "muted-green",
        "css_class": "rmc-wf-status--superseded",
    },
    "remediated": {
        "key": "remediated",
        "label": "Remediated",
        "tone": "resolved",
        "color": "muted-green",
        "css_class": "rmc-wf-status--superseded",
    },
}


def status_meta(status: str, *, remediated: bool = False) -> dict[str, str]:
    """Return display metadata for a workflow status."""

    key = str(status or "waiting").strip().lower() or "waiting"
    if remediated:
        key = "superseded"
    meta = dict(WORKFLOW_STATUS_TAXONOMY.get(key) or WORKFLOW_STATUS_TAXONOMY["waiting"])
    meta["raw_status"] = str(status or "")
    return meta


def status_taxonomy_payload() -> dict[str, dict[str, str]]:
    """JSON-safe taxonomy payload."""

    return {key: dict(value) for key, value in WORKFLOW_STATUS_TAXONOMY.items()}


def recovery_context_for_run(
    run_payload: dict[str, Any],
    *,
    action_count: int = 0,
    remediated: bool = False,
) -> dict[str, Any]:
    """Compact AI/copilot context for a run shown in the recovery deck."""

    remediation = run_payload.get("suggested_remediation") or {}
    status = run_payload.get("status") or ""
    return {
        "run_id": run_payload.get("id"),
        "workflow_key": run_payload.get("workflow_key", ""),
        "status": status,
        "status_meta": status_meta(status, remediated=remediated),
        "tenant_schema": run_payload.get("tenant_schema", ""),
        "school_id": run_payload.get("school_id", ""),
        "current_step": run_payload.get("current_step_name", ""),
        "progress_percent": run_payload.get("progress_percent", 0),
        "auto_fix_kind": remediation.get("auto_fix_kind", ""),
        "auto_fix_available": bool(remediation.get("auto_fix_available")),
        "action_count": action_count,
        "human_action": remediation.get("human_action", ""),
        "remediated": remediated,
    }
