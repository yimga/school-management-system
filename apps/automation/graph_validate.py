"""
Validate relational visual workflow graphs before publish (Salesforce-style guardrails).
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.apps import apps


def validate_workflow_for_publish(workflow_id: int) -> list[str]:
    """
    Return human-readable errors; empty list means the workflow can be published.

    Rules:
    - At least one trigger, one condition, and one action node.
    - Graph must be weakly connected from the first trigger (all nodes reachable via edges).
    - ``workflow.trigger_event`` must match the visual trigger node config when present.
    """
    Workflow = apps.get_model("automation", "Workflow")
    WorkflowNode = apps.get_model("automation", "WorkflowNode")
    WorkflowEdge = apps.get_model("automation", "WorkflowEdge")

    wf = Workflow.objects.filter(pk=workflow_id).first()
    if wf is None:
        return ["workflow_not_found"]

    nodes = list(WorkflowNode.objects.filter(workflow=wf))
    if not nodes:
        return ["no_nodes"]

    kinds = {n.kind for n in nodes}
    K = getattr(WorkflowNode, "Kind", None)
    trig = K.TRIGGER if K else "trigger"
    cond = K.CONDITION if K else "condition"
    act = K.ACTION if K else "action"
    if trig not in kinds:
        return ["missing_trigger_node"]
    if cond not in kinds:
        return ["missing_condition_node"]
    if act not in kinds:
        return ["missing_action_node"]

    edges = list(WorkflowEdge.objects.filter(workflow=wf).select_related("source", "target"))
    by_pk: dict[int, Any] = {n.pk: n for n in nodes}
    adj: dict[int, list[int]] = defaultdict(list)
    for e in edges:
        if e.source_id in by_pk and e.target_id in by_pk:
            adj[e.source_id].append(e.target_id)
            adj[e.target_id].append(e.source_id)

    triggers = [n for n in nodes if n.kind == trig]
    start = triggers[0].pk
    seen = set()
    stack = [start]
    while stack:
        cur = stack.pop()
        if cur in seen:
            continue
        seen.add(cur)
        for nb in adj.get(cur, []):
            if nb not in seen:
                stack.append(nb)

    if len(seen) != len(nodes):
        return ["disconnected_graph"]

    trig_cfg = triggers[0].config if isinstance(triggers[0].config, dict) else {}
    hinted = (
        str(trig_cfg.get("trigger_event") or trig_cfg.get("event") or "").strip()
    )
    if hinted and hinted != (wf.trigger_event or "").strip():
        return ["trigger_mismatch"]

    return []
