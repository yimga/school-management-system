"""
Help search intelligence — logging, zero-result aggregates, typeahead (batch 1339).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Count
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import get_language

from apps.portal.kb_synonyms import expand_query_synonyms


def log_help_search(
    request,
    *,
    query: str,
    result_count: int,
    is_operator: bool | None = None,
) -> None:
    """Fingerprinted search telemetry (no raw query text in DB)."""
    q = (query or "").strip()
    if not q:
        return
    try:
        from apps.feedback.models import HelpSearchQueryLog, SupportDeflectionEvent

        if is_operator is None:
            from apps.portal.kb_context import is_operator_help_request

            is_operator = is_operator_help_request(request)
        fp = SupportDeflectionEvent.fingerprint(q)
        HelpSearchQueryLog.objects.create(
            school=getattr(request, "school", None),
            query_fingerprint=fp,
            result_count=max(0, int(result_count)),
            is_operator=bool(is_operator),
            locale=(get_language() or "")[:12],
        )
        if int(result_count) == 0 and fp:
            from apps.portal.help_content_gaps import ensure_content_gap_task

            ensure_content_gap_task(fingerprint=fp)
    except Exception:
        pass


def zero_result_fingerprints(*, days: int = 7, limit: int = 10) -> list[dict[str, Any]]:
    """Top zero-result query fingerprints for operator content backlog."""
    since = timezone.now() - timedelta(days=days)
    try:
        from apps.feedback.models import HelpSearchQueryLog

        rows = (
            # tenant-isolation-allow: operator-zero-result-fingerprint-aggregate-no-raw-query
            HelpSearchQueryLog.objects.filter(
                created_at__gte=since,
                result_count=0,
            )
            .values("query_fingerprint")
            .annotate(n=Count("id"))
            .order_by("-n")[:limit]
        )
        return [{"fingerprint": r["query_fingerprint"], "count": r["n"]} for r in rows]
    except Exception:
        return []


def deflection_rate_summary(*, days: int = 7) -> dict[str, Any]:
    """North-star deflection metrics for operator hub."""
    since = timezone.now() - timedelta(days=days)
    try:
        from apps.feedback.models import SupportDeflectionEvent

        # tenant-isolation-allow: cross-tenant operator aggregate; fingerprint-only telemetry
        qs = SupportDeflectionEvent.objects.filter(created_at__gte=since)
        suggested = qs.filter(outcome="suggested").count()
        dismissed = qs.filter(outcome="dismissed").count()
        opened = qs.filter(outcome="opened").count()
        submitted = qs.filter(outcome="submitted").count()
        total = qs.count()
        resolved = dismissed + opened
        rate = round((resolved / suggested * 100), 1) if suggested else 0.0
        return {
            "available": True,
            "total_events": total,
            "suggested": suggested,
            "dismissed": dismissed,
            "opened": opened,
            "submitted": submitted,
            "deflection_rate_pct": rate,
        }
    except Exception:
        return {"available": False}


def kb_typeahead_suggestions(request, query: str, *, limit: int = 8) -> list[dict[str, Any]]:
    """Lightweight title suggestions for help-center search typeahead."""
    q = expand_query_synonyms((query or "").strip())
    if len(q) < 2:
        return []
    from apps.portal.views_kb import _published_kb_for_request
    from apps.portal.kb_search import search_kb_articles

    base_qs = _published_kb_for_request(request)
    ranked = search_kb_articles(base_qs, q, limit=limit)
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
                "url": url,
                "score": round(float(score), 3),
            }
        )
    return out
