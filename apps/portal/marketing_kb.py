"""
Sovereign marketing KB search — published global articles for runmycampus.com.

Reads from the platform help corpus tenant schema (MARKETING_KB_TENANT_SLUG /
TENANT_EXAMPLE_SLUG) when django-tenants is enabled; otherwise the default DB.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Any, Generator

from django.conf import settings
from django.db.models import Q, QuerySet

from apps.portal.kb_context import filter_kb_articles_by_region, published_kb_queryset
from apps.portal.kb_search import search_kb_articles
from apps.portal.kb_synonyms import expand_query_synonyms
from apps.portal.models_kb import HelpAudience, KBArticle

logger = logging.getLogger(__name__)


def marketing_kb_tenant_slug() -> str:
    explicit = (getattr(settings, "MARKETING_KB_TENANT_SLUG", None) or "").strip()
    if explicit:
        return explicit
    return (getattr(settings, "TENANT_EXAMPLE_SLUG", None) or "demo-school").strip()


@contextmanager
def marketing_kb_schema_context() -> Generator[None, None, None]:
    """Enter the schema that stores platform-global marketing KB articles."""
    use_tenants = getattr(settings, "USE_DJANGO_TENANTS", False)
    if not use_tenants:
        yield
        return
    schema_name = None
    slug = marketing_kb_tenant_slug()
    try:
        from apps.schools.models import School

        school = School.objects.filter(slug=slug, is_active=True).first()
        if school is not None:
            client = getattr(school, "tenant_client", None)
            schema_name = (getattr(client, "schema_name", None) or "").strip() or None
    except Exception:
        logger.warning("marketing_kb: could not resolve schema for slug=%s", slug)
    if not schema_name:
        yield
        return
    try:
        from django_tenants.utils import schema_context
    except ImportError:
        yield
        return
    with schema_context(schema_name):
        yield


def marketing_kb_queryset(*, country_code: str = "", plan_tier: str = "") -> QuerySet:
    """Published global articles visible on the public marketing surface."""
    qs = published_kb_queryset().filter(
        is_global_article=True,
        help_audience__in=[HelpAudience.BOTH, HelpAudience.TENANT],
    )
    qs = qs.filter(Q(target_roles=[]) | Q(target_roles__isnull=True))
    if country_code or plan_tier:
        qs = filter_kb_articles_by_region(qs, country_code, plan_tier)
    return qs


def marketing_kb_search(
    query: str,
    *,
    country_code: str = "",
    plan_tier: str = "",
    limit: int = 25,
) -> list[tuple[KBArticle, float]]:
    q = expand_query_synonyms((query or "").strip())
    if not q:
        return []
    with marketing_kb_schema_context():
        base = marketing_kb_queryset(country_code=country_code, plan_tier=plan_tier)
        return search_kb_articles(base, q, limit=limit)


def marketing_kb_typeahead(
    query: str,
    *,
    country_code: str = "",
    plan_tier: str = "",
    limit: int = 8,
) -> list[dict[str, Any]]:
    q = expand_query_synonyms((query or "").strip())
    if len(q) < 2:
        return []
    ranked = marketing_kb_search(
        q, country_code=country_code, plan_tier=plan_tier, limit=limit
    )
    out: list[dict[str, Any]] = []
    for article, score in ranked:
        out.append(
            {
                "slug": article.slug,
                "title": article.title or "",
                "summary": (article.summary or "")[:200],
                "score": round(float(score), 3),
            }
        )
    return out


def marketing_kb_hub_bundle(
    *,
    country_code: str = "",
    plan_tier: str = "",
    featured_limit: int = 6,
    category_limit: int = 8,
) -> dict[str, Any]:
    """Featured articles + category counts for the public marketing help hub."""
    from apps.portal.models_kb import KBCategory

    with marketing_kb_schema_context():
        base = marketing_kb_queryset(country_code=country_code, plan_tier=plan_tier)
        article_count = base.count()
        featured = list(
            base.filter(is_featured=True).order_by("-view_count", "-updated_at")[
                :featured_limit
            ]
        )
        if len(featured) < featured_limit:
            extra = list(
                base.exclude(pk__in=[a.pk for a in featured]).order_by(
                    "-view_count", "-updated_at"
                )[: featured_limit - len(featured)]
            )
            featured = featured + extra
        cat_ids = base.values_list("category_id", flat=True).distinct()
        categories = []
        for cat in KBCategory.objects.filter(pk__in=cat_ids, is_active=True).order_by(
            "display_order", "name"
        )[:category_limit]:
            count = base.filter(category=cat).count()
            if count:
                categories.append({"category": cat, "article_count": count})
    return {
        "article_count": article_count,
        "featured_articles": featured,
        "categories": categories,
    }


def marketing_kb_semantic_search(
    query: str,
    *,
    country_code: str = "",
    plan_tier: str = "",
    limit: int = 25,
) -> list[tuple[KBArticle, float]]:
    """Vector similarity search over the marketing corpus when embeddings exist."""
    q = (query or "").strip()
    if len(q) < 3:
        return []
    try:
        from services.ai_memory import get_embedding_for_text

        embedding = get_embedding_for_text(q, max_tokens=512)
    except Exception:
        embedding = None
    if not embedding:
        return []
    try:
        from apps.schools.models import School

        school = School.objects.filter(
            slug=marketing_kb_tenant_slug(), is_active=True
        ).first()
    except Exception:
        school = None
    from apps.portal.kb_embeddings import search_kb_articles_by_embedding

    with marketing_kb_schema_context():
        hits = search_kb_articles_by_embedding(
            school=school,
            query_embedding=embedding,
            limit=limit * 2,
            operator=False,
        )
        allowed = set(
            marketing_kb_queryset(country_code=country_code, plan_tier=plan_tier).values_list(
                "pk", flat=True
            )
        )
        return [(a, s) for a, s in hits if a.pk in allowed][:limit]


def marketing_kb_search_hybrid(
    query: str,
    *,
    country_code: str = "",
    plan_tier: str = "",
    limit: int = 25,
) -> tuple[list[tuple[KBArticle, float]], str]:
    """
    Text search first; semantic fallback when text returns nothing.
    Returns (results, mode) where mode is ``text`` or ``semantic``.
    """
    text_hits = marketing_kb_search(
        query, country_code=country_code, plan_tier=plan_tier, limit=limit
    )
    if text_hits:
        return text_hits, "text"
    semantic_hits = marketing_kb_semantic_search(
        query, country_code=country_code, plan_tier=plan_tier, limit=limit
    )
    return semantic_hits, "semantic" if semantic_hits else "text"


def marketing_kb_category_by_slug(
    category_slug: str,
    *,
    country_code: str = "",
    plan_tier: str = "",
) -> dict[str, Any] | None:
    """Category metadata + published marketing articles (batch 1360)."""
    from apps.portal.models_kb import KBCategory

    slug = (category_slug or "").strip()
    if not slug:
        return None
    with marketing_kb_schema_context():
        category = KBCategory.objects.filter(slug=slug, is_active=True).first()
        if category is None:
            return None
        articles = list(
            marketing_kb_queryset(country_code=country_code, plan_tier=plan_tier)
            .filter(category=category)
            .order_by("-is_featured", "display_order", "-view_count")
        )
    return {
        "category": category,
        "articles": articles,
        "article_count": len(articles),
    }


def marketing_kb_article_by_slug(
    slug: str,
    *,
    country_code: str = "",
    plan_tier: str = "",
) -> KBArticle | None:
    slug = (slug or "").strip()
    if not slug:
        return None
    with marketing_kb_schema_context():
        return (
            marketing_kb_queryset(country_code=country_code, plan_tier=plan_tier)
            .filter(slug=slug)
            .first()
        )
