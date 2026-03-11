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
    ) -> list[dict[str, Any]]:
        """Return stored rows with similar embedding (cosine similarity in Python)."""
        if not embedding:
            return []
        try:
            from apps.siteconfig.models import AIEmbeddingStore
            qs = AIEmbeddingStore.objects.filter(scope=scope).order_by("-created_at")[:500]
            if school_id:
                qs = qs.filter(school_id=school_id)
            rows = list(qs.values("id", "conversation_id", "text_hash", "metadata", "embedding", "created_at"))
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
            scored = [(cos_sim(row["embedding"], embedding), row) for row in rows]
            scored.sort(key=lambda x: -x[0])
            return [r for _, r in scored[:limit]]
        except Exception as e:
            logger.warning("AIMemoryService search failed: %s", e)
            return []
