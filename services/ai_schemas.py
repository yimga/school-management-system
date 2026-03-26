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


# --- Theme & experience recommendations ---


class RecommendationItem(TypedDict, total=False):
    title: str
    category: str
    description: str
    rationale: str
    fit: str


class ThemeExperienceSchema(TypedDict, total=False):
    suggestions: list[RecommendationItem]
    rationale: str


def _coerce_recommendation_items(raw: Any, *, limit: int = 20) -> list[RecommendationItem]:
    if not isinstance(raw, list):
        return []
    items: list[RecommendationItem] = []
    for item in raw[:limit]:
        if isinstance(item, dict):
            items.append({
                "title": str(item.get("title") or item.get("name") or item.get("label") or "")[:160],
                "category": str(item.get("category", ""))[:96],
                "description": str(item.get("description", ""))[:512],
                "rationale": str(item.get("rationale", ""))[:512],
                "fit": str(item.get("fit", ""))[:256],
            })
        elif isinstance(item, (str, int, float)):
            text = str(item)[:256]
            items.append({"title": text, "description": text})
    return items


def validate_theme_experience(raw: dict[str, Any]) -> ThemeExperienceSchema:
    if not isinstance(raw, dict):
        raise ValueError("theme_experience must be a JSON object")
    return {
        "suggestions": _coerce_recommendation_items(raw.get("suggestions")),
        "rationale": str(raw.get("rationale", ""))[:1024],
    }


# --- Report recommendation ---


class ReportRecommendationSchema(TypedDict, total=False):
    recommendations: list[RecommendationItem]


def validate_report_recommend(raw: dict[str, Any]) -> ReportRecommendationSchema:
    if not isinstance(raw, dict):
        raise ValueError("report_recommend must be a JSON object")
    return {
        "recommendations": _coerce_recommendation_items(raw.get("recommendations")),
    }


# --- Design Studio structured output ---


class DesignStudioSchema(TypedDict, total=False):
    suggestions: list[RecommendationItem]
    components: list[str]


def validate_design_studio(raw: dict[str, Any]) -> DesignStudioSchema:
    if not isinstance(raw, dict):
        raise ValueError("design_studio must be a JSON object")
    components = raw.get("components")
    if not isinstance(components, list):
        components = []
    return {
        "suggestions": _coerce_recommendation_items(raw.get("suggestions")),
        "components": [str(component)[:128] for component in components[:20] if isinstance(component, (str, int, float))],
    }


# --- Dashboard / pack recommendations ---


class DashboardPackRecommendSchema(TypedDict, total=False):
    dashboards: list[RecommendationItem]
    packs: list[RecommendationItem]
    rationale: str


def validate_dashboard_pack_recommend(raw: dict[str, Any]) -> DashboardPackRecommendSchema:
    if not isinstance(raw, dict):
        raise ValueError("dashboard_pack_recommend must be a JSON object")
    return {
        "dashboards": _coerce_recommendation_items(raw.get("dashboards")),
        "packs": _coerce_recommendation_items(raw.get("packs")),
        "rationale": str(raw.get("rationale", ""))[:1024],
    }


# --- Marketplace recommendations ---


class MarketplaceRecommendSchema(TypedDict, total=False):
    recommendations: list[RecommendationItem]
    rationale: str


def validate_marketplace_recommend(raw: dict[str, Any]) -> MarketplaceRecommendSchema:
    if not isinstance(raw, dict):
        raise ValueError("marketplace_recommend must be a JSON object")
    return {
        "recommendations": _coerce_recommendation_items(raw.get("recommendations")),
        "rationale": str(raw.get("rationale", ""))[:1024],
    }


# --- Guided assistant (shared JSON shape for domain copilots: Studio, interop, runtime, etc.) ---


class GuidedAssistantAction(TypedDict, total=False):
    title: str
    detail: str


class GuidedAssistantSchema(TypedDict, total=False):
    summary: str
    actions: list[GuidedAssistantAction]
    cautions: list[str]
    references: list[str]


def validate_guided_assistant(raw: dict[str, Any]) -> GuidedAssistantSchema:
    if not isinstance(raw, dict):
        raise ValueError("guided_assistant must be a JSON object")
    summary = str(raw.get("summary", ""))[:4000]
    actions_in = raw.get("actions")
    if not isinstance(actions_in, list):
        actions_in = []
    actions: list[GuidedAssistantAction] = []
    for a in actions_in[:25]:
        if isinstance(a, dict):
            actions.append({
                "title": str(a.get("title", ""))[:256],
                "detail": str(a.get("detail", ""))[:1500],
            })
    cautions_in = raw.get("cautions")
    if not isinstance(cautions_in, list):
        cautions_in = []
    cautions = [str(c)[:512] for c in cautions_in[:15] if isinstance(c, (str, int, float))]
    refs_in = raw.get("references")
    if not isinstance(refs_in, list):
        refs_in = []
    references = [str(r)[:512] for r in refs_in[:15] if isinstance(r, (str, int, float))]
    return {
        "summary": summary,
        "actions": actions,
        "cautions": cautions,
        "references": references,
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
