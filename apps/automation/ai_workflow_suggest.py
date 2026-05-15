"""AI workflow step suggestions.

Operators authoring an automation in the workflow studio sometimes know
*roughly* what should happen ("when a payment posts, message the
guardian, and update the ledger") but not the exact node sequence. This
helper turns a natural-language intent into a JSON node list the studio
can drop into the canvas as a draft.

Used by the workflow studio's "Ask AI" affordance. Returns ``None`` when
AI is disabled.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


# Stable allow-list of node kinds the studio knows how to render. Extend
# in tandem with the studio's node palette.
SUPPORTED_NODE_KINDS: tuple[str, ...] = (
    "trigger.event",
    "action.send_notification",
    "action.send_sms",
    "action.send_email",
    "action.post_ledger_entry",
    "action.create_task",
    "action.update_status",
    "action.escalate",
    "condition.if",
    "delay.timer",
)


@dataclass
class WorkflowSuggestion:
    nodes: list[dict[str, Any]]
    reasoning: str
    confidence: float
    tier: str


def propose_workflow(
    *,
    school: Any | None,
    intent_text: str,
    trigger_event: str | None = None,
    allowed_node_kinds: list[str] | None = None,
) -> WorkflowSuggestion | None:
    """Propose a workflow node list for the given natural-language intent.

    ``trigger_event`` should be a value from ``Workflow.trigger_event``.
    ``allowed_node_kinds`` overrides ``SUPPORTED_NODE_KINDS`` when the
    tenant's studio has a custom palette.
    """
    from services.ai_helpers import invoke_json_task

    if not (intent_text or "").strip():
        return None

    allowed = list(allowed_node_kinds or SUPPORTED_NODE_KINDS)
    prompt = _build_prompt(intent_text, trigger_event, allowed)

    parsed = invoke_json_task(
        school=school,
        task_type_name="WORKFLOW_DRAFT",
        prompt=prompt,
        prompt_type="automation.workflow_draft",
        content_sensitivity="standard",
    )
    if parsed is None:
        return None

    obj, meta = parsed
    raw_nodes = obj.get("nodes") or []
    if not isinstance(raw_nodes, list):
        return None

    nodes: list[dict[str, Any]] = []
    for n in raw_nodes:
        if not isinstance(n, dict):
            continue
        kind = str(n.get("kind", "")).strip().lower()
        if kind not in allowed:
            continue
        nodes.append({
            "kind": kind,
            "label": str(n.get("label", "")).strip()[:64],
            "params": n.get("params") if isinstance(n.get("params"), dict) else {},
        })
    if not nodes:
        return None

    return WorkflowSuggestion(
        nodes=nodes,
        reasoning=str(obj.get("reasoning", "")).strip()[:280],
        confidence=_clip(obj.get("confidence")),
        tier=str(meta.get("tier", "unknown")),
    )


def _build_prompt(intent_text: str, trigger_event: str | None, allowed: list[str]) -> str:
    return (
        "You are an automation studio assistant. Translate the operator's "
        "intent into a workflow as an ordered list of nodes. Return JSON only.\n"
        "Every node MUST use a kind from the allowed list.\n\n"
        f"Allowed kinds: {allowed}\n"
        f"Trigger event (may be empty): {trigger_event or ''}\n"
        f"Intent: {intent_text!r}\n\n"
        'Return JSON exactly: {"nodes": [{"kind": "<one of allowed>", '
        '"label": "<short>", "params": {<optional kv>}}], '
        '"reasoning": "<one sentence>", "confidence": <0..1>}'
    )


def _clip(raw: Any) -> float:
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, v))
