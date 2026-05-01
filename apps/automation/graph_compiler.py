"""
Compile relational WorkflowNode + WorkflowEdge graphs into DSL for workflow_engine.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.apps import apps

Workflow = apps.get_model("automation", "Workflow")
WorkflowNode = apps.get_model("automation", "WorkflowNode")


def normalize_action_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """Map Salesforce-style names to engine handlers."""
    if not isinstance(raw, dict):
        return {"type": "notify", "params": {}}
    t = str(raw.get("type") or "").strip().lower()
    alias = {
        "send_message": "notify",
        "notify_parent": "notify",
        "notify_teacher": "notify",
        "notify_admin": "notify",
        "create_task": "create_record",
        "update_record": "update_field",
        "trigger_webhook": "webhook",
    }
    t = alias.get(t, t) or "notify"
    out = dict(raw)
    if str(raw.get("type") or "").strip().lower() == "create_report":
        out["type"] = "emit_event"
        params = dict(raw.get("params") or {})
        params.setdefault("event_type", "workflow.report_requested")
        if "payload" not in params:
            params["payload"] = {}
        out["params"] = params
        return out
    out["type"] = t
    if "params" not in out:
        out["params"] = {}
    return out


def compile_workflow_to_dsl(workflow: Workflow) -> dict[str, Any]:
    """
    DFS from first trigger node; collects conditions and actions in traversal order.

    Condition node ``config`` may be:
    - ``{"condition": {...}}`` single rule
    - ``{"conditions": [{...}, ...]}``
    - or flat ``{"field", "op", "value"}``
    """
    nodes = {n.external_id: n for n in workflow.nodes.all()}
    edges = workflow.edges.select_related("source", "target").all()
    adj: dict[str, list[str]] = defaultdict(list)
    for e in edges:
        adj[e.source.external_id].append(e.target.external_id)

    triggers = [n for n in nodes.values() if n.kind == WorkflowNode.Kind.TRIGGER]
    if not triggers:
        return {
            "trigger": workflow.trigger_event,
            "conditions": [],
            "actions": [],
        }

    start = triggers[0].external_id
    visited: set[str] = set()
    order: list[str] = []

    def dfs(nid: str) -> None:
        if nid in visited:
            return
        visited.add(nid)
        order.append(nid)
        for nxt in adj.get(nid, []):
            dfs(nxt)

    dfs(start)

    conditions: list[dict[str, Any]] = []
    actions: list[dict[str, Any]] = []

    for nid in order:
        node = nodes.get(nid)
        if not node:
            continue
        cfg = node.config if isinstance(node.config, dict) else {}

        if node.kind == WorkflowNode.Kind.CONDITION:
            if isinstance(cfg.get("conditions"), list):
                for c in cfg["conditions"]:
                    if isinstance(c, dict):
                        conditions.append(c)
            elif isinstance(cfg.get("condition"), dict):
                conditions.append(cfg["condition"])
            elif cfg.get("field"):
                conditions.append(
                    {k: cfg[k] for k in ("field", "op", "value") if k in cfg}
                )

        elif node.kind == WorkflowNode.Kind.ACTION:
            raw_action = cfg.get("action")
            if isinstance(raw_action, dict):
                actions.append(normalize_action_dict(raw_action))
            elif cfg.get("type"):
                actions.append(normalize_action_dict(cfg))

        elif node.kind == WorkflowNode.Kind.DELAY:
            seconds = int(cfg.get("seconds") or cfg.get("delay_seconds") or 0)
            seconds = max(0, min(seconds, 300))
            actions.append({"type": "delay", "params": {"seconds": seconds}})

    return {
        "trigger": workflow.trigger_event,
        "conditions": conditions,
        "actions": actions,
    }
