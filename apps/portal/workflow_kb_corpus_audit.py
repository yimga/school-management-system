"""
Phase 9 audit-driven workflow KB articles — fills gaps from workflow_help_kb_faq_audit.json.

Hand-written P0 entries in ``workflow_kb_corpus.py`` take precedence (custom slugs).
Generated rows use ``slug == workflow_id`` for stable deep links.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_AUDIT_PATH = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "generated"
    / "workflow_help_kb_faq_audit.json"
)

_AUDIENCE_ROLES: dict[str, list[str]] = {
    "teacher": ["TEACHER"],
    "parent": ["PARENT"],
    "student": ["STUDENT"],
    "school_admin": ["ADMIN"],
    "partner": ["ADMIN"],
    "operator": [],
}


def _category_slug(workflow_id: str) -> str:
    wid = workflow_id.lower()
    if any(k in wid for k in ("finance", "payroll", "payment", "billing", "invoice")):
        return "finance"
    if any(k in wid for k in ("evals", "grade", "syllabus", "academics", "marks")):
        return "grading-assessment"
    if any(k in wid for k in ("migration", "connector", "maa")):
        return "system-admin"
    if any(k in wid for k in ("communication", "announcement", "narrative")):
        return "communication"
    if any(k in wid for k in ("compliance", "erasure", "dsar")):
        return "compliance"
    if "report" in wid:
        return "reporting"
    if "marketplace" in wid or "publisher" in wid:
        return "marketplace"
    if any(k in wid for k in ("siteconfig", "configure", "onboarding", "wizard")):
        return "system-admin"
    if any(k in wid for k in ("observability", "incident", "platform-runtime")):
        return "operations"
    if "studio" in wid:
        return "studio-os"
    return "operations"


def _title_from_workflow_id(workflow_id: str) -> str:
    core = workflow_id.split("-", 1)[-1] if "-" in workflow_id else workflow_id
    words = re.sub(r"[-_]+", " ", core).strip()
    return words[:1].upper() + words[1:] if words else workflow_id


def _content_from_audit_row(row: dict[str, Any]) -> str:
    from apps.portal.workflow_kb_corpus_enrich import enriched_content_from_audit_row

    return enriched_content_from_audit_row(row)


def _help_audience(audience: str) -> str:
    return "OPERATOR" if audience == "operator" else "TENANT"


def load_phase9_audit_rows() -> list[dict[str, Any]]:
    if not _AUDIT_PATH.is_file():
        return []
    data = json.loads(_AUDIT_PATH.read_text(encoding="utf-8"))
    return list(data.get("workflows") or [])


def build_audit_workflow_kb_corpus(
    *,
    skip_workflow_ids: set[str] | None = None,
) -> tuple[dict[str, Any], ...]:
    """Articles for audit workflows without template-only help (excluding hand-written ids)."""
    skip = skip_workflow_ids or set()
    out: list[dict[str, Any]] = []
    for row in load_phase9_audit_rows():
        wid = (row.get("workflow_id") or "").strip()
        if not wid or wid in skip:
            continue
        path = (row.get("help_article_path") or "").strip()
        status = row.get("help_article_status") or ""
        # Template-backed runbooks (Phase 9 spot-check exists) — do not duplicate.
        if status == "exists" and path.startswith("templates/"):
            continue
        audience = row.get("audience") or "school_admin"
        out.append(
            {
                "workflow_id": wid,
                "slug": wid,
                "title": _title_from_workflow_id(wid),
                "summary": (row.get("recommendation") or _title_from_workflow_id(wid))[
                    :240
                ],
                "category_slug": _category_slug(wid),
                "target_roles": list(_AUDIENCE_ROLES.get(audience, ["ADMIN"])),
                "help_audience": _help_audience(audience),
                "tags": f"{audience},{row.get('priority', 'p2')},workflow,phase9",
                "content": _content_from_audit_row(row),
            }
        )
    return tuple(out)
