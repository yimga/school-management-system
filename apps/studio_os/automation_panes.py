"""Real data for the Automation Studio panes that used to be explainer-only.

Two panes shipped as static prose despite having real backing engines:

* **Conflict detection** — ``apps.automation.graph_validate.validate_workflow_for_publish``
  already validates a visual workflow's graph, and multiple PUBLISHED+active
  workflows on the SAME trigger event are a real activation conflict. This
  module runs both checks across the tenant's own workflows and returns a
  structured report the pane renders.
* **Replay / rollback** — ``WorkflowRunLog`` is the real execution audit for the
  visual engine. This module returns the tenant's recent runs so replay/rollback
  operates on real instances, not prose.

Everything here is tenant-scoped by ``school`` and read-only. When there is no
bound school (e.g. the manager host without impersonation) the helpers return an
``available: False`` payload so the pane degrades to guidance instead of erroring.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.db import DatabaseError, OperationalError, ProgrammingError

_PANE_QUERY_ERRORS = (
    AttributeError,
    DatabaseError,
    ImportError,
    OperationalError,
    ProgrammingError,
    TypeError,
    ValueError,
)

# Cap the per-report validation fan-out (each workflow costs a few queries).
_MAX_WORKFLOWS = 200  # magic-number-allow: conflict-report validation fan-out cap
_MAX_RECENT_RUNS = 25  # magic-number-allow: replay pane recent-run window


def _resolve_school(request) -> Any:
    return getattr(request, "school", None) or getattr(request, "tenant", None)


def build_workflow_conflict_report(request) -> dict:
    """Real conflict report for the tenant's visual workflows.

    Combines two real signals:
      * per-workflow graph validation errors (``validate_workflow_for_publish``);
      * trigger overlaps — >1 PUBLISHED + active workflow on the same event, which
        all fire together and can conflict.
    """
    school = _resolve_school(request)
    if school is None or getattr(school, "pk", None) is None:
        return {"available": False}
    try:
        from apps.automation.graph_validate import validate_workflow_for_publish
        from apps.automation.workflow_graph_models import Workflow

        workflows = list(
            Workflow.objects.filter(school=school).order_by("trigger_event", "name")[
                :_MAX_WORKFLOWS
            ]
        )
    except _PANE_QUERY_ERRORS:
        return {"available": False}

    issues: list[dict] = []
    by_trigger: dict[str, list] = defaultdict(list)
    for wf in workflows:
        try:
            errs = validate_workflow_for_publish(wf.id)
        except _PANE_QUERY_ERRORS:
            errs = ["validation_unavailable"]
        if errs:
            issues.append(
                {
                    "name": wf.name,
                    "id": wf.id,
                    "status": wf.get_status_display(),
                    "errors": errs,
                }
            )
        if wf.status == Workflow.Status.PUBLISHED and wf.is_active:
            by_trigger[wf.trigger_event].append(wf)

    overlaps = [
        {
            "trigger": trig,
            "count": len(wfs),
            "workflows": [w.name for w in wfs],
        }
        for trig, wfs in sorted(by_trigger.items())
        if len(wfs) > 1
    ]
    return {
        "available": True,
        "total_workflows": len(workflows),
        "issues": issues,
        "trigger_overlaps": overlaps,
        "clean": not issues and not overlaps,
    }


def recent_workflow_runs(request) -> dict:
    """Recent visual-workflow runs for the tenant (real replay/rollback targets)."""
    school = _resolve_school(request)
    if school is None or getattr(school, "pk", None) is None:
        return {"available": False, "runs": []}
    try:
        from apps.automation.workflow_graph_models import WorkflowRunLog

        runs = list(
            WorkflowRunLog.objects.filter(workflow__school=school)
            .select_related("workflow")
            .order_by("-created_at")[:_MAX_RECENT_RUNS]
        )
    except _PANE_QUERY_ERRORS:
        return {"available": False, "runs": []}
    return {"available": True, "runs": runs, "count": len(runs)}
