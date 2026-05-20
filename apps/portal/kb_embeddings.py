"""
KB article vector embeddings — cosine search over ``KBArticle.vector_embedding``.
"""

from __future__ import annotations

import logging
import math
from typing import Any

from django.db import models
from django.db.models import QuerySet

from apps.portal.kb_context import filter_kb_articles_by_school, published_kb_queryset
from apps.portal.models_kb import HelpAudience, KBArticle

logger = logging.getLogger(__name__)

DEFLECTION_SCORE_THRESHOLD = 0.88


def effective_deflection_threshold(*, school: Any = None) -> float:
    """
    Calibrate deflection gate from corpus helpfulness (batch 1341).
    Stricter threshold when published articles skew unhelpful.
    """
    base = DEFLECTION_SCORE_THRESHOLD
    try:
        qs = _published_scope_qs(school=school, operator=False)
        helpful = 0
        unhelpful = 0
        for row in qs.values("helpful_count", "unhelpful_count")[:500]:
            helpful += int(row.get("helpful_count") or 0)
            unhelpful += int(row.get("unhelpful_count") or 0)
        if helpful + unhelpful >= 10 and unhelpful > helpful * 2:
            return min(0.95, base + 0.04)
    except Exception:
        pass
    return base


def _locale_codes_for_request() -> list[str]:
    try:
        from django.utils.translation import get_language

        lang = (get_language() or "en")[:12].lower()
        if not lang:
            return ["en"]
        primary = lang.split("-")[0]
        codes = [lang]
        if primary and primary not in codes:
            codes.append(primary)
        if "en" not in codes:
            codes.append("en")
        return codes
    except Exception:
        return ["en"]


def embedding_source_text(article: KBArticle) -> str:
    parts = [article.title or "", article.summary or "", article.tags or ""]
    return "\n".join(p for p in parts if p).strip()


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return -1.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    norm_l = math.sqrt(sum(a * a for a in left))
    norm_r = math.sqrt(sum(b * b for b in right))
    if norm_l <= 0 or norm_r <= 0:
        return -1.0
    return dot / (norm_l * norm_r)


def refresh_kb_article_embedding(article: KBArticle, *, save: bool = True) -> bool:
    """Compute and persist ``vector_embedding`` from title/summary/tags."""
    try:
        from services.ai_memory import get_embedding_for_text
    except ImportError:
        return False
    text = embedding_source_text(article)
    if not text:
        return False
    embedding = get_embedding_for_text(text, max_tokens=512)
    if not embedding:
        return False
    article.vector_embedding = embedding
    if save:
        article.save(update_fields=["vector_embedding"])
    return True


def filter_kb_queryset_by_locale(qs: QuerySet[KBArticle]) -> QuerySet[KBArticle]:
    if not hasattr(KBArticle, "locale"):
        return qs
    codes = _locale_codes_for_request()
    return qs.filter(models.Q(locale__in=codes) | models.Q(locale=""))


def filter_kb_queryset_by_locale_with_fallback(
    qs: QuerySet[KBArticle],
) -> QuerySet[KBArticle]:
    """
    Prefer request locale; if no rows, widen to English + locale-agnostic (batch 1354).
    """
    scoped = filter_kb_queryset_by_locale(qs)
    if scoped.exists():
        return scoped
    codes = _locale_codes_for_request()
    if "en" in codes:
        return qs.filter(models.Q(locale__in=["en", ""]) | models.Q(locale=""))
    return qs.filter(models.Q(locale="en") | models.Q(locale=""))


def sibling_locales_for_article(article: KBArticle) -> QuerySet[KBArticle]:
    """Articles in the same translation group (batch 1350)."""
    if not getattr(article, "locale_group_id", None):
        return KBArticle.objects.none()
    gid = (article.locale_group_id or "").strip()
    if not gid:
        return KBArticle.objects.none()
    school_id = getattr(article, "school_id", None)
    if school_id:
        return KBArticle.objects.filter(
            locale_group_id=gid, school_id=school_id
        ).exclude(pk=article.pk)
    return KBArticle.objects.filter(
        locale_group_id=gid, school__isnull=True
    ).exclude(pk=article.pk)


def _published_scope_qs(*, school: Any, operator: bool) -> QuerySet[KBArticle]:
    audience = (
        [HelpAudience.OPERATOR, HelpAudience.BOTH]
        if operator
        else [HelpAudience.TENANT, HelpAudience.BOTH]
    )
    qs = published_kb_queryset().filter(help_audience__in=audience)
    qs = filter_kb_articles_by_school(qs, school)
    return filter_kb_queryset_by_locale(qs)


def search_kb_articles_by_embedding(
    *,
    school: Any,
    query_embedding: list[float],
    limit: int = 4,
    operator: bool = False,
) -> list[tuple[KBArticle, float]]:
    if not query_embedding:
        return []
    try:
        from apps.portal.kb_pgvector import search_kb_pgvector

        school_id = str(getattr(school, "pk", None) or "") or None
        pg_hits = search_kb_pgvector(
            school_id=school_id,
            query_embedding=query_embedding,
            limit=limit,
            operator=operator,
        )
        if pg_hits:
            ids = [pk for pk, _ in pg_hits]
            score_map = {pk: sc for pk, sc in pg_hits}
            school_pk = getattr(school, "pk", None)
            if school_pk:
                hit_qs = KBArticle.objects.filter(pk__in=ids, school_id=school_pk)
            else:
                hit_qs = KBArticle.objects.filter(pk__in=ids, school__isnull=True)
            articles = {
                a.pk: a for a in filter_kb_articles_by_school(hit_qs, school)
            }
            return [
                (articles[pk], score_map[pk])
                for pk in ids
                if pk in articles
            ]
    except Exception:
        pass
    qs = _published_scope_qs(school=school, operator=operator).exclude(
        vector_embedding=[]
    )
    scored: list[tuple[KBArticle, float]] = []
    for article in qs.iterator(chunk_size=200):
        vec = article.vector_embedding
        if not isinstance(vec, list) or len(vec) < 8:
            continue
        try:
            floats = [float(v) for v in vec]
        except (TypeError, ValueError):
            continue
        score = cosine_similarity(query_embedding, floats)
        if score > 0.05:
            scored.append((article, score))
    scored.sort(key=lambda row: row[1], reverse=True)
    return scored[:limit]


def kb_context_lines_from_vector_search(
    *,
    school: Any,
    user_query: str,
    limit: int = 4,
    operator: bool = False,
) -> list[str]:
    try:
        from services.ai_memory import get_embedding_for_text
    except ImportError:
        return []
    embedding = get_embedding_for_text(user_query, max_tokens=512)
    if not embedding:
        return []
    hits = search_kb_articles_by_embedding(
        school=school,
        query_embedding=embedding,
        limit=limit,
        operator=operator,
    )
    lines: list[str] = []
    for article, score in hits:
        snippet = (article.summary or "")[:400].replace("\n", " ").strip()
        if snippet:
            lines.append(f"- KB [{score:.2f}]: {article.title}: {snippet}")
    return lines
