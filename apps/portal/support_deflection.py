"""
Support ticket deflection — vector + keyword KB matches before ticket submit.
"""

from __future__ import annotations

import logging
from typing import Any

from django.urls import reverse

from apps.portal.kb_context import is_operator_help_request
from apps.portal.help_governance import ai_help_enabled_for_request
from apps.portal.kb_embeddings import (
    effective_deflection_threshold,
    search_kb_articles_by_embedding,
)

logger = logging.getLogger(__name__)


def _article_payload(request, article, score: float) -> dict[str, Any]:
    try:
        url = reverse("kb:kb_article", kwargs={"article_slug": article.slug})
    except Exception:
        url = ""
    return {
        "slug": article.slug,
        "title": article.title or "",
        "summary": (article.summary or "")[:280],
        "score": round(float(score), 4),
        "url": url,
        "id": str(article.pk),
    }


def find_deflection_candidates(
    request,
    *,
    query_text: str,
    limit: int = 3,
    threshold: float | None = None,
) -> dict[str, Any]:
    """
    Return KB articles scoring at or above *threshold* (cosine similarity).
    Falls back to keyword suggest_help_resources when embeddings unavailable.
    """
    query = (query_text or "").strip()[:2000]
    school = getattr(request, "school", None)
    operator = is_operator_help_request(request)
    if not ai_help_enabled_for_request(request):
        return {
            "query": query,
            "threshold": threshold or effective_deflection_threshold(school=school),
            "method": "disabled",
            "blocking": False,
            "articles": [],
        }
    if threshold is None:
        threshold = effective_deflection_threshold(school=school)
    articles: list[dict[str, Any]] = []
    method = "none"

    if query and school is not None:
        try:
            from services.ai_memory import get_embedding_for_text

            embedding = get_embedding_for_text(query, max_tokens=512)
            if embedding:
                hits = search_kb_articles_by_embedding(
                    school=school,
                    query_embedding=embedding,
                    limit=max(limit, 6),
                    operator=operator,
                )
                for article, score in hits:
                    if score >= threshold:
                        articles.append(_article_payload(request, article, score))
                if articles:
                    method = "vector"
        except Exception as exc:
            logger.debug("deflection vector search skipped: %s", exc)

    if not articles and query:
        try:
            from apps.feedback.services import suggest_help_resources

            bundle = suggest_help_resources(
                request,
                description=query,
                limit=limit,
            )
            for article in bundle.get("articles") or []:
                articles.append(
                    {
                        "slug": getattr(article, "slug", ""),
                        "title": getattr(article, "title", ""),
                        "summary": (getattr(article, "summary", "") or "")[:280],
                        "score": 0.0,
                        "url": reverse(
                            "kb:kb_article",
                            kwargs={"article_slug": article.slug},
                        )
                        if getattr(article, "slug", None)
                        else "",
                        "id": str(getattr(article, "pk", "")),
                    }
                )
            if articles:
                method = "keyword"
        except Exception as exc:
            logger.debug("deflection keyword fallback skipped: %s", exc)

    blocking = bool(articles) and method == "vector" and any(
        row.get("score", 0) >= threshold for row in articles
    )
    try:
        from apps.feedback.models import HelpSearchQueryLog, SupportDeflectionEvent
        from django.utils import translation

        if query:
            HelpSearchQueryLog.objects.create(
                school=school,
                query_fingerprint=SupportDeflectionEvent.fingerprint(query),
                result_count=len(articles),
                is_operator=operator,
                locale=(translation.get_language() or "")[:12],
            )
    except Exception as exc:
        logger.debug("help search log skipped: %s", exc)
    return {
        "query": query,
        "threshold": threshold,
        "method": method,
        "blocking": blocking,
        "articles": articles[:limit],
    }


def record_deflection_event(
    request,
    *,
    query_text: str,
    articles: list[dict[str, Any]],
    outcome: str,
    surface: str = "support_ticket",
) -> None:
    """Persist aggregate deflection telemetry (no raw query text when redacted)."""
    try:
        from apps.feedback.models import SupportDeflectionEvent

        school = getattr(request, "school", None)
        top = articles[0] if articles else {}
        SupportDeflectionEvent.objects.create(
            school=school,
            user=request.user if getattr(request, "user", None) and request.user.is_authenticated else None,
            surface=surface,
            outcome=outcome,
            top_score=float(top.get("score") or 0),
            article_slug=(top.get("slug") or "")[:120],
            query_fingerprint=SupportDeflectionEvent.fingerprint(query_text),
            is_operator=is_operator_help_request(request),
        )
    except Exception as exc:
        logger.warning("record_deflection_event failed: %s", exc)
