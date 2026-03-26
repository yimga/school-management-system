"""
World Engine D.2: AI memory service using PGVector / AIEmbeddingStore.
Single store for embeddings; used by chat or support agent when enabled.
Uses services.embeddings get_embedding_provider() for pluggable Ollama / OpenAI-compatible backends.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _normalize_actor_roles(actor_roles: list[str] | tuple[str, ...] | set[str] | None) -> set[str]:
    if not actor_roles:
        return set()
    return {str(role).strip().lower() for role in actor_roles if str(role).strip()}


def _metadata_visible_to_actor(
    metadata: dict[str, Any] | None,
    *,
    actor_roles: list[str] | tuple[str, ...] | set[str] | None = None,
    actor_is_staff: bool = False,
    actor_is_superuser: bool = False,
) -> bool:
    if not isinstance(metadata, dict):
        return True
    if actor_is_superuser:
        return True
    if metadata.get("staff_only") and not actor_is_staff:
        return False
    allowed_roles = metadata.get("allowed_roles")
    if isinstance(allowed_roles, (list, tuple, set)):
        required = {str(role).strip().lower() for role in allowed_roles if str(role).strip()}
        if required and not (_normalize_actor_roles(actor_roles) & required):
            return False
    visibility = str(metadata.get("visibility") or "").strip().lower()
    if visibility in {"staff", "operator"} and not actor_is_staff:
        return False
    return True


def get_embedding_for_text(text: str, *, max_tokens: int = 8192) -> list[float] | None:
    """Return embedding for text using the configured embedding provider (router)."""
    try:
        from services.embeddings import get_embedding_provider
        return get_embedding_provider().embed(text, max_tokens=max_tokens)
    except Exception as e:
        logger.warning("get_embedding_for_text failed: %s", e)
        return None


class AIMemoryService:
    """
    Store and retrieve AI-related embeddings for RAG or chat context.
    Uses AIEmbeddingStore; when feature/config enabled, inference or chat can call this.
    """

    @staticmethod
    def store(
        school_id: str | None,
        conversation_id: str,
        scope: str,
        text: str,
        metadata: dict | None = None,
    ) -> bool:
        """Store text embedding. Returns True if stored."""
        if not text or not conversation_id:
            return False
        try:
            from apps.siteconfig.models import AIEmbeddingStore
            embedding = get_embedding_for_text(text, max_tokens=8192)
            if not embedding:
                return False
            text_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
            AIEmbeddingStore.objects.create(
                school_id=school_id,
                conversation_id=conversation_id,
                scope=scope,
                text_hash=text_hash,
                embedding=embedding,
                metadata=metadata or {},
            )
            return True
        except Exception as e:
            logger.warning("AIMemoryService store failed: %s", e)
            return False

    @staticmethod
    def search_similar(
        school_id: str | None,
        scope: str,
        embedding: list[float],
        limit: int = 5,
        *,
        actor_roles: list[str] | tuple[str, ...] | set[str] | None = None,
        actor_is_staff: bool = False,
        actor_is_superuser: bool = False,
    ) -> list[dict[str, Any]]:
        """Return stored rows with similar embedding (cosine similarity in Python)."""
        if not embedding:
            return []
        try:
            from apps.siteconfig.models import AIEmbeddingStore
            from django.db.models import Q

            qs = AIEmbeddingStore.objects.filter(scope=scope)
            if school_id:
                qs = qs.filter(Q(school_id=school_id) | Q(school_id__isnull=True))
            qs = qs.order_by("-created_at")[:500]
            rows = list(
                qs.values(
                    "id",
                    "school_id",
                    "conversation_id",
                    "text_hash",
                    "metadata",
                    "embedding",
                    "created_at",
                )
            )
            # Simple cosine similarity (no pgvector operator)
            def cos_sim(a, b):
                if not a or not b or len(a) != len(b):
                    return 0.0
                dot = sum(x * y for x, y in zip(a, b))
                na = sum(x * x for x in a) ** 0.5
                nb = sum(x * x for x in b) ** 0.5
                if na * nb == 0:
                    return 0.0
                return dot / (na * nb)
            visible_rows = [
                row
                for row in rows
                if _metadata_visible_to_actor(
                    row.get("metadata"),
                    actor_roles=actor_roles,
                    actor_is_staff=actor_is_staff,
                    actor_is_superuser=actor_is_superuser,
                )
            ]
            def rank_score(row: dict[str, Any]) -> float:
                base = cos_sim(row["embedding"], embedding)
                # Policy RAG: when a tenant context is present, prefer that school's bundle
                # over global (null school_id) rows at equal vector similarity.
                if scope == "policy" and school_id:
                    rid = row.get("school_id")
                    if rid is not None and str(rid) == str(school_id):
                        return base + 0.25
                return base

            scored = [(rank_score(row), row) for row in visible_rows]
            scored.sort(key=lambda x: -x[0])
            return [r for _, r in scored[:limit]]
        except Exception as e:
            logger.warning("AIMemoryService search failed: %s", e)
            return []
