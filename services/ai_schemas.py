"""
Structured output schemas for AI gateway. All operational task types that return JSON
must validate against these schemas. Used by gateway.invoke(..., response_schema=...).
"""
from __future__ import annotations

import json
from typing import Any, TypedDict

# --- Workflow draft (workflow_draft task type) ---


class WorkflowStep(TypedDict, total=False):
    action: str
    role: str
    config: dict[str, Any]


class WorkflowDraftSchema(TypedDict, total=False):
    name: str
    trigger_type: str
    steps: list[WorkflowStep]
    description: str


def validate_workflow_draft(raw: dict[str, Any]) -> WorkflowDraftSchema:
    if not isinstance(raw, dict):
        raise ValueError("workflow_draft must be a JSON object")
    name = raw.get("name") or ""
    trigger_type = raw.get("trigger_type") or "manual"
    steps = raw.get("steps")
    if not isinstance(steps, list):
        steps = []
    out_steps: list[WorkflowStep] = []
    for s in steps[:50]:
        if isinstance(s, dict):
            out_steps.append({
                "action": str(s.get("action", ""))[:256],
                "role": str(s.get("role", ""))[:128],
                "config": s.get("config") if isinstance(s.get("config"), dict) else {},
            })
    return {
        "name": str(name)[:256],
        "trigger_type": str(trigger_type)[:64],
        "steps": out_steps,
        "description": str(raw.get("description", ""))[:1024],
    }


# --- Policy explanation (policy_explain task type) ---


class PolicyDifference(TypedDict, total=False):
    field: str
    current: str
    proposed: str


class PolicyExplainSchema(TypedDict, total=False):
    summary: str
    differences: list[PolicyDifference]
    warnings: list[str]


def validate_policy_explain(raw: dict[str, Any]) -> PolicyExplainSchema:
    if not isinstance(raw, dict):
        raise ValueError("policy_explain must be a JSON object")
    summary = str(raw.get("summary", ""))[:2000]
    diffs = raw.get("differences")
    if not isinstance(diffs, list):
        diffs = []
    out_diffs: list[PolicyDifference] = []
    for d in diffs[:30]:
        if isinstance(d, dict):
            out_diffs.append({
                "field": str(d.get("field", ""))[:128],
                "current": str(d.get("current", ""))[:512],
                "proposed": str(d.get("proposed", ""))[:512],
            })
    warnings = raw.get("warnings")
    if not isinstance(warnings, list):
        warnings = []
    out_warnings = [str(w)[:512] for w in warnings[:20] if isinstance(w, (str, int, float))]
    return {"summary": summary, "differences": out_diffs, "warnings": out_warnings}


# --- Migration mapping (migration_mapping task type) ---


class MigrationMappingItem(TypedDict, total=False):
    source_field: str
    target_field: str
    confidence: float
    notes: str


def validate_migration_mapping(raw: Any) -> list[MigrationMappingItem]:
    if isinstance(raw, dict) and "mappings" in raw:
        raw = raw["mappings"]
    if not isinstance(raw, list):
        raise ValueError("migration_mapping must be a JSON array (or object with 'mappings' array)")
    out: list[MigrationMappingItem] = []
    for m in raw[:100]:
        if isinstance(m, dict):
            conf = m.get("confidence")
            if isinstance(conf, (int, float)):
                conf = max(0.0, min(1.0, float(conf)))
            else:
                conf = 0.0
            out.append({
                "source_field": str(m.get("source_field", ""))[:256],
                "target_field": str(m.get("target_field", ""))[:256],
                "confidence": conf,
                "notes": str(m.get("notes", ""))[:512],
            })
    return out


# --- Document classification (doc_classify task type) ---


class DocumentClassifySchema(TypedDict, total=False):
    category: str
    tags: list[str]
    confidence: float


def validate_doc_classify(raw: dict[str, Any]) -> DocumentClassifySchema:
    if not isinstance(raw, dict):
        raise ValueError("doc_classify must be a JSON object")
    tags = raw.get("tags")
    if not isinstance(tags, list):
        tags = []
    out_tags = [str(t)[:64] for t in tags[:20] if isinstance(t, (str, int, float))]
    conf = raw.get("confidence")
    if isinstance(conf, (int, float)):
        conf = max(0.0, min(1.0, float(conf)))
    else:
        conf = 0.0
    return {
        "category": str(raw.get("category", ""))[:128],
        "tags": out_tags,
        "confidence": conf,
    }


# --- JSON extraction from model response (prose + JSON) ---


def extract_json_from_text(text: str) -> dict[str, Any] | list[Any] | None:
    """Extract first complete JSON object or array from text. Returns None if invalid."""
    if not text or not isinstance(text, str):
        return None
    start = text.find("{")
    if start < 0:
        start = text.find("[")
        if start < 0:
            return None
    depth = 0
    in_string = False
    escape = False
    quote = None
    end = -1
    for i, c in enumerate(text[start:], start=start):
        if escape:
            escape = False
            continue
        if c == "\\" and in_string:
            escape = True
            continue
        if in_string:
            if c == quote:
                in_string = False
            continue
        if c in ('"', "'"):
            in_string = True
            quote = c
            continue
        if c in "{[":
            depth += 1
        elif c in "}]":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end <= start:
        return None
    try:
        return json.loads(text[start:end])
    except json.JSONDecodeError:
        return None
