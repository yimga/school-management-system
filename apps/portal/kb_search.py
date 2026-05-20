"""Ranked KB article search (Move 4).

Backend-aware: uses Postgres full-text search when available, otherwise falls
back to icontains with a simple term-frequency score so the top hit is more
than just whichever article happens to be most recent.
"""

from __future__ import annotations

import re

from django.db import connection
from django.db.models import Q

from apps.portal.kb_synonyms import expand_query_synonyms


_WORD_RE = re.compile(r"[A-Za-z0-9_]+")


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _WORD_RE.findall(text or "")]


def _is_postgres() -> bool:
    return "postgresql" in connection.vendor.lower()


def search_kb_articles(
    queryset,
    query: str,
    *,
    limit: int = 25,
):
    """Return a list of (article, score) tuples sorted by score desc.

    `queryset` is the base KBArticle queryset (already filtered by
    tenant/visibility). `query` is the raw user query string.
    """

    q = expand_query_synonyms((query or "").strip())
    if not q:
        return []

    if _is_postgres():
        try:
            from django.contrib.postgres.search import (
                SearchQuery,
                SearchRank,
                SearchVector,
            )

            vector = (
                SearchVector("title", weight="A")
                + SearchVector("summary", weight="B")
                + SearchVector("content", weight="C")
            )
            sq = SearchQuery(q)
            rows = (
                queryset.annotate(rank=SearchRank(vector, sq))
                .filter(rank__gt=0)
                .order_by("-rank")[:limit]
            )
            return [(a, float(getattr(a, "rank", 0))) for a in rows]
        except Exception:
            pass

    # Portable fallback: gather candidates with icontains, then rerank in
    # Python by simple term-frequency * field-weight.
    terms = _tokenize(q)
    if not terms:
        return []
    or_q = Q()
    for t in terms:
        or_q |= Q(title__icontains=t) | Q(summary__icontains=t) | Q(content__icontains=t)
    candidates = list(queryset.filter(or_q)[: limit * 4])

    def _score(article) -> float:
        title = (article.title or "").lower()
        summary = (article.summary or "").lower()
        content = (article.content or "").lower()
        score = 0.0
        for t in terms:
            score += 4.0 * title.count(t)
            score += 2.0 * summary.count(t)
            score += 1.0 * content.count(t)
        return score

    scored = [(a, _score(a)) for a in candidates]
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return [(a, s) for a, s in scored[:limit] if s > 0]
