"""Visual workflow versioning (Move 2).

Each "publish" of a visual workflow snapshots the current nodes+edges into a
WorkflowVersion row. WorkflowRunLog is bound to a version so an in-flight run
keeps executing the graph it was triggered on, even if the publisher edits.
"""

from __future__ import annotations

from django.db import transaction
from django.db.models import Max

from apps.automation.workflow_graph_models import (
    Workflow,
    WorkflowRunLog,
    WorkflowVersion,
)


def _serialize_graph(workflow: Workflow) -> dict:
    nodes = [
        {
            "external_id": n.external_id,
            "kind": n.kind,
            "config": n.config,
            "position": n.position,
        }
        for n in workflow.nodes.all().order_by("external_id")
    ]
    edges = [
        {
            "source": e.source.external_id,
            "target": e.target.external_id,
            "label": e.label,
        }
        for e in workflow.edges.select_related("source", "target").all()
    ]
    return {"nodes": nodes, "edges": edges, "trigger_event": workflow.trigger_event}


@transaction.atomic
def publish_visual_workflow_version(
    workflow: Workflow,
    *,
    notes: str = "",
    published_by=None,
) -> WorkflowVersion:
    """Snapshot the current graph as a new WorkflowVersion."""

    WorkflowVersion.objects.filter(workflow=workflow, is_current=True).update(
        is_current=False
    )
    last = WorkflowVersion.objects.filter(workflow=workflow).aggregate(
        m=Max("version_number")
    )["m"] or 0
    next_no = last + 1
    wv = WorkflowVersion.objects.create(
        workflow=workflow,
        version_number=next_no,
        graph_snapshot=_serialize_graph(workflow),
        trigger_event=workflow.trigger_event,
        notes=notes,
        is_current=True,
        published_by=published_by if (published_by and getattr(published_by, "is_authenticated", False)) else None,
    )
    workflow.current_version = next_no
    workflow.status = Workflow.Status.PUBLISHED
    workflow.save(update_fields=["current_version", "status", "updated_at"])
    return wv


def current_version_for(workflow: Workflow) -> WorkflowVersion | None:
    return WorkflowVersion.objects.filter(workflow=workflow, is_current=True).first()


def bind_run_to_current_version(run: WorkflowRunLog) -> WorkflowRunLog:
    if run.workflow_version_id:
        return run
    wv = current_version_for(run.workflow)
    if wv is None:
        wv = publish_visual_workflow_version(run.workflow, notes="auto-init")
    run.workflow_version = wv
    run.save(update_fields=["workflow_version"])
    return run
