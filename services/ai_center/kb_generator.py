"""KB / FAQ draft generation — human review required before tenant publish."""

from __future__ import annotations

import uuid
from typing import Any

from services.ai_center.audit import emit_ai_center_event
from services.ai_center.indexing import get_feature_evidence, search_by_route


def _draft_row(
    *,
    title: str,
    body: str,
    module: str,
    route: str | None,
    evidence_ids: list[str],
    audience: str,
) -> dict[str, Any]:
    if not evidence_ids:
        raise ValueError("KB draft requires at least one evidence doc_id")
    draft_id = uuid.uuid4().hex
    emit_ai_center_event(
        "ai_kb_draft_created",
        audit_id=draft_id,
        route_context=route or "",
        payload_summary={
            "title": title[:120],
            "module": module,
            "audience": audience,
            "evidence_count": len(evidence_ids),
            "status": "draft",
        },
    )
    return {
        "draft_id": draft_id,
        "title": title,
        "body": body,
        "module": module,
        "route": route,
        "evidence_ids": evidence_ids,
        "audience": audience,
        "status": "draft",
        "tenant_visible": False,
    }


def generate_kb_article_from_route(route: str, *, audience: str = "tenant") -> dict[str, Any]:
    hits = search_by_route(route)
    evidence_ids = [h["doc_id"] for h in hits if h.get("doc_id")]
    if not evidence_ids:
        raise ValueError("no_evidence_for_route")
    title = f"Guide: {route}"
    body = "\n".join(f"- {h.get('text', '')[:300]}" for h in hits[:6])
    return _draft_row(
        title=title,
        body=body,
        module=hits[0].get("module", "routes"),
        route=route,
        evidence_ids=evidence_ids,
        audience=audience,
    )


def generate_kb_article_from_code_change(
    module: str,
    *,
    change_summary: str,
    route: str | None = None,
) -> dict[str, Any]:
    evidence = get_feature_evidence(module)
    evidence_ids = [e["doc_id"] for e in evidence if e.get("doc_id")][:8]
    if not evidence_ids:
        raise ValueError("no_evidence_for_module")
    return _draft_row(
        title=f"Update: {module}",
        body=change_summary[:4000],
        module=module,
        route=route,
        evidence_ids=evidence_ids,
        audience="operator",
    )


def generate_faqs_for_module(module: str, *, limit: int = 5) -> list[dict[str, Any]]:
    evidence = get_feature_evidence(module)[:limit]
    faqs = []
    for row in evidence:
        faqs.append(
            {
                "question": f"How do I use {module} on RunMyCampus?",
                "answer_draft": row.get("text", "")[:500],
                "evidence_ids": [row["doc_id"]],
                "status": "draft",
            }
        )
    return faqs


def generate_tenant_guide(module: str, route: str | None = None) -> dict[str, Any]:
    return generate_kb_article_from_route(route or f"/{module}/", audience="tenant")


def generate_operator_runbook(module: str) -> dict[str, Any]:
    return generate_kb_article_from_code_change(
        module,
        change_summary=f"Operator runbook for {module} (draft — review before publish).",
    )


def generate_release_note_from_feature(feature_key: str) -> dict[str, Any]:
    return generate_kb_article_from_code_change(
        feature_key,
        change_summary=f"Release note draft for {feature_key}.",
    )


def propose_help_topics_from_errors(error_codes: list[str]) -> list[dict[str, Any]]:
    topics = []
    for code in error_codes[:20]:
        topics.append(
            {
                "topic": f"Troubleshoot {code}",
                "evidence_ids": [],
                "status": "candidate",
            }
        )
    return topics


def propose_faqs_from_feedback(feedback_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for row in feedback_rows[:20]:
        subject = (row.get("subject") or row.get("category") or "feedback")[:80]
        out.append(
            {
                "question": f"FAQ candidate: {subject}",
                "answer_draft": (row.get("summary") or "")[:400],
                "evidence_ids": row.get("evidence_ids") or [],
                "status": "candidate",
            }
        )
    return out
