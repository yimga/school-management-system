"""RAG / knowledge-base indexing contract for AI Center."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from django.conf import settings

from services.ai_center.constants import DATA_DEFAULTER_PREFIX

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[2]
INVENTORY_JSON = ROOT / "docs" / "generated" / "ai_center_platform_inventory.json"
_INDEX_CACHE: list[dict[str, Any]] | None = None


def _load_inventory() -> dict[str, Any]:
    if INVENTORY_JSON.is_file():
        try:
            return json.loads(INVENTORY_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            logger.warning("ai_center inventory load failed: %s", exc)
    return {"apps": [], "url_pattern_sample": [], "generated_proof_artifacts": []}


def build_platform_index() -> dict[str, Any]:
    """Build metadata-only platform index from inventory + route reflection."""
    inv = _load_inventory()
    docs: list[dict[str, Any]] = []
    for app in inv.get("apps", []):
        label = app.get("app_label", "")
        docs.append(
            {
                "doc_id": f"app:{label}",
                "module": label,
                "kind": "app_ledger",
                "text": f"RunMyCampus app `{label}` at {app.get('path', '')}",
                "route": None,
                "roles": ["operator", "tenant"],
            }
        )
    try:
        from services.ai.reflection import DynamicSystemInspector

        inspector = DynamicSystemInspector()
        for row in inspector.get_route_registry()[:400]:
            path = row.get("url_path") or ""
            name = row.get("name") or ""
            docs.append(
                {
                    "doc_id": f"route:{name or path}",
                    "module": (name or path).split(":")[0] if ":" in (name or "") else "routes",
                    "kind": "route_metadata",
                    "text": f"Route {path} ({name}) perms={','.join(row.get('required_permissions') or [])}",
                    "route": path,
                    "roles": ["operator"],
                }
            )
    except Exception as exc:
        logger.debug("route index skipped: %s", exc)
    for proof in inv.get("generated_proof_artifacts", [])[:100]:
        docs.append(
            {
                "doc_id": f"proof:{proof}",
                "module": "proof",
                "kind": "proof_artifact",
                "text": f"Generated proof artifact {proof}",
                "route": None,
                "roles": ["operator"],
            }
        )
    global _INDEX_CACHE
    _INDEX_CACHE = docs
    return {"document_count": len(docs), "metadata_only": True, "generated_from": str(INVENTORY_JSON)}


def _documents() -> list[dict[str, Any]]:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        build_platform_index()
    return _INDEX_CACHE or []


def index_document(
    *,
    doc_id: str,
    text: str,
    module: str,
    route: str | None = None,
    roles: list[str] | None = None,
    kind: str = "manual",
) -> dict[str, Any]:
    """Append one document to the in-process index (session-scoped)."""
    row = {
        "doc_id": doc_id,
        "module": module,
        "kind": kind,
        "text": text[:4000],
        "route": route,
        "roles": roles or ["operator", "tenant"],
    }
    _documents().append(row)
    return row


def _score(query: str, doc: dict[str, Any]) -> float:
    q = query.lower()
    text = (doc.get("text") or "").lower()
    if not q:
        return 0.0
    score = 0.0
    for token in q.split():
        if len(token) < 3:
            continue
        if token in text:
            score += 1.0
        if token in (doc.get("module") or "").lower():
            score += 2.0
        if token in (doc.get("route") or "").lower():
            score += 3.0
    return score


def search_platform_knowledge(
    query: str,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    max_docs = limit or int(getattr(settings, "AI_CENTER_MAX_CONTEXT_DOCS", 8))
    ranked = sorted(_documents(), key=lambda d: _score(query, d), reverse=True)
    return [d for d in ranked if _score(query, d) > 0][:max_docs]


def search_by_route(route: str, *, limit: int = 5) -> list[dict[str, Any]]:
    route = (route or "").strip()
    hits = [d for d in _documents() if route and route in (d.get("route") or "")]
    if not hits:
        hits = search_platform_knowledge(route, limit=limit)
    return hits[:limit]


def search_by_role(role: str, *, limit: int = 8) -> list[dict[str, Any]]:
    role_low = (role or "").lower()
    hits = [
        d
        for d in _documents()
        if role_low in [r.lower() for r in (d.get("roles") or [])]
    ]
    return hits[:limit]


def search_by_module(module: str, *, limit: int = 8) -> list[dict[str, Any]]:
    mod = (module or "").lower()
    hits = [d for d in _documents() if mod and mod in (d.get("module") or "").lower()]
    return hits[:limit]


def get_feature_evidence(feature_key: str) -> list[dict[str, Any]]:
    return search_platform_knowledge(feature_key, limit=12)


def get_missing_context_reason(query: str) -> str:
    if search_platform_knowledge(query, limit=1):
        return ""
    return DATA_DEFAULTER_PREFIX
