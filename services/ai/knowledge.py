"""Help-center and embedding retrieval for engine-room support."""

from __future__ import annotations

import logging
from typing import Any

from services.ai.tenant_isolation import PlatformTier, SecurityIsolationException, TenantContextEnforcer

logger = logging.getLogger(__name__)


def _user_permission_labels(user: Any, *, school: Any | None) -> list[str]:
    labels: list[str] = []
    role = getattr(user, "role", None)
    if role:
        labels.append(f"ROLE_{str(role).upper()}")
    if getattr(user, "is_staff", False):
        labels.append("IS_STAFF")
    if getattr(user, "is_superuser", False):
        labels.append("IS_SUPERUSER")
    try:
        from services.ai_permissions import get_ai_permission_for_user

        for task in (
            "support_suggest",
            "admin_copilot",
            "config_explain",
            "policy_explain",
            "billing_usage_explain",
        ):
            if get_ai_permission_for_user(user, task, school):
                labels.append(f"AI_TASK_{task.upper()}")
    except ImportError:
        pass
    return list(dict.fromkeys(labels))


def retrieve_knowledge_snippets(
    *,
    user: Any,
    school: Any | None,
    user_query: str,
    scope: PlatformTier,
    actor_roles: list[str] | None = None,
    actor_is_staff: bool = False,
    actor_is_superuser: bool = False,
    limit: int = 5,
) -> tuple[list[str], list[dict[str, Any]]]:
    """
    Return (plain-text bullets, rag_snippets metadata for gateway/rules fallback).
    """
    enforcer = TenantContextEnforcer(user, school=school)
    tenant_scope = enforcer.resolve_scope()
    school_id = tenant_scope.tenant_id
    lines: list[str] = []
    rag_rows: list[dict[str, Any]] = []

    # Tenant KB vector + keyword search (django-tenants schema).
    if scope == PlatformTier.SCHOOL_TENANT and school is not None:
        try:
            from apps.portal.kb_embeddings import kb_context_lines_from_vector_search

            for line in kb_context_lines_from_vector_search(
                school=school,
                user_query=user_query,
                limit=limit,
                operator=False,
            ):
                lines.append(line)
                rag_rows.append(
                    {
                        "scope": "help",
                        "metadata": {"source": "kb_vector", "text": line[2:][:400]},
                    }
                )
        except Exception as exc:
            logger.debug("tenant KB vector search skipped: %s", exc)
        try:
            from apps.portal.support_ai_context import build_kb_context_block

            kb_block = build_kb_context_block("", user_query, school)
            if kb_block:
                for raw in kb_block.splitlines():
                    line = raw.strip()
                    if line.startswith("- "):
                        lines.append(line)
                        rag_rows.append(
                            {"scope": "help", "metadata": {"source": "tenant_kb", "text": line[2:][:400]}}
                        )
        except Exception as exc:
            logger.debug("tenant KB context skipped: %s", exc)

    # Vector store (scope help / config).
    try:
        from services.ai_memory import AIMemoryService, get_embedding_for_text

        embedding = get_embedding_for_text(user_query, max_tokens=512)
        if embedding:
            memory_scope = "config" if scope == PlatformTier.PLATFORM_MANAGER else "help"
            global_only = scope == PlatformTier.PLATFORM_MANAGER and school_id is None
            hits = AIMemoryService.search_similar(
                school_id,
                memory_scope,
                embedding,
                limit=limit,
                global_only=global_only,
                actor_roles=actor_roles or [],
                actor_is_staff=actor_is_staff,
                actor_is_superuser=actor_is_superuser,
            )
            for hit in hits:
                row_sid = hit.get("school_id")
                try:
                    enforcer.assert_retrieval_allowed(
                        row_school_id=str(row_sid) if row_sid is not None else None,
                        global_row=row_sid is None,
                    )
                except SecurityIsolationException:
                    continue
                meta = hit.get("metadata") if isinstance(hit.get("metadata"), dict) else {}
                text = (meta.get("text") or meta.get("summary") or meta.get("title") or "").strip()
                if not text and meta.get("source"):
                    text = str(meta.get("source"))
                if not text:
                    continue
                bullet = f"- {text[:400]}"
                lines.append(bullet)
                rag_rows.append({"scope": memory_scope, "metadata": meta})
    except Exception as exc:
        logger.debug("embedding retrieval skipped: %s", exc)

    return lines[:limit], rag_rows[:limit]


def permission_labels_for_user(user: Any, *, school: Any | None) -> list[str]:
    return _user_permission_labels(user, school=school)
