"""Suggest KB articles for forum topics and deflection (batch 1359)."""

from __future__ import annotations

from typing import Any

from django.urls import reverse

from apps.portal.kb_search import search_kb_articles
from apps.portal.views_kb import _published_kb_for_request


def suggested_kb_for_text(
    request,
    text: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Ranked published KB articles for forum topic body or deflection context."""
    q = (text or "").strip()
    if len(q) < 3:
        return []
    base = _published_kb_for_request(request)
    ranked = search_kb_articles(base, q, limit=limit)
    out: list[dict[str, Any]] = []
    for article, score in ranked:
        try:
            url = reverse("kb:kb_article", kwargs={"article_slug": article.slug})
        except Exception:
            url = ""
        out.append(
            {
                "slug": article.slug,
                "title": article.title or "",
                "summary": (article.summary or "")[:160],
                "url": url,
                "score": round(float(score), 3),
            }
        )
    return out
