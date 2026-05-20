"""
Optional pgvector retrieval for KB articles (batch 1351).

Falls back to JSON cosine in ``kb_embeddings`` when disabled or column absent.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db import connection

logger = logging.getLogger(__name__)


def kb_pgvector_enabled() -> bool:
    return bool(getattr(settings, "KB_PGVECTOR_ENABLED", False)) and (
        connection.vendor == "postgresql"
    )


def _embedding_vec_column_exists() -> bool:
    if not kb_pgvector_enabled():
        return False
    try:
        with connection.cursor() as cur:
            # tenant-isolation-allow: schema-introspection-for-pgvector-column-exists
            cur.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_name = 'portal_kbarticle'
                  AND column_name = 'embedding_vec'
                LIMIT 1
                """
            )
            return cur.fetchone() is not None
    except Exception:
        return False


def search_kb_pgvector(
    *,
    school_id: str | None,
    query_embedding: list[float],
    limit: int = 4,
    operator: bool = False,
) -> list[tuple[int, float]]:
    """Return list of (article_pk, score). Empty when unavailable."""
    if not query_embedding or not _embedding_vec_column_exists():
        return []
    placeholder = "[" + ",".join(f"{float(x):.8f}" for x in query_embedding) + "]"
    if operator:
        audience_filter = " AND help_audience IN ('OPERATOR', 'BOTH')"
    else:
        audience_filter = " AND help_audience IN ('TENANT', 'BOTH')"
    school_filter = ""
    params: list[Any] = [placeholder, placeholder]
    if school_id:
        school_filter = " AND (school_id = %s OR school_id IS NULL)"
        params.append(str(school_id))
    params.extend([placeholder, limit])
    sql = f"""
        SELECT id, 1.0 - (embedding_vec <=> %s::vector) AS score
        FROM portal_kbarticle
        WHERE status = 'PUBLISHED'
          AND embedding_vec IS NOT NULL
          {audience_filter}
          {school_filter}
        ORDER BY embedding_vec <=> %s::vector
        LIMIT %s
    """
    try:
        with connection.cursor() as cur:
            # tenant-isolation-allow: operator-kb-vector-search-school-filter-in-sql
            cur.execute(sql, params)
            return [(int(row[0]), float(row[1])) for row in cur.fetchall()]
    except Exception as exc:
        logger.debug("kb pgvector search skipped: %s", exc)
        return []
