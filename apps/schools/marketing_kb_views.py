"""Public marketing knowledge-base search (batch 1357)."""

from __future__ import annotations

from django.core.paginator import Paginator
from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET

from apps.portal.marketing_kb import (
    marketing_kb_article_by_slug,
    marketing_kb_category_by_slug,
    marketing_kb_search_hybrid,
    marketing_kb_typeahead,
)
from apps.siteconfig.list_search import normalize_list_search_query


def _marketing_kb_region(request) -> tuple[str, str]:
    country = (request.GET.get("country") or "").strip()[:2].upper()
    plan = (request.GET.get("plan") or "").strip()
    return country, plan


@require_GET
def marketing_kb_search_view(request):
    """Full-text search over sovereign global KB articles on runmycampus.com."""
    query = normalize_list_search_query(request.GET.get("q"))
    country, plan = _marketing_kb_region(request)
    ranked, search_mode = marketing_kb_search_hybrid(
        query, country_code=country, plan_tier=plan, limit=100
    )
    articles = [a for a, _score in ranked]
    paginator = Paginator(articles, 12)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "marketing/kb_search_results.html",
        {
            "query": query,
            "page_obj": page,
            "result_count": len(articles),
            "search_mode": search_mode,
            "typeahead_url": reverse("marketing_kb_typeahead"),
            "article_url_name": "marketing_kb_article",
        },
    )


@require_GET
def marketing_kb_category_view(request, category_slug: str):
    """Dedicated category landing for sovereign marketing KB (batch 1360)."""
    country, plan = _marketing_kb_region(request)
    bundle = marketing_kb_category_by_slug(
        category_slug, country_code=country, plan_tier=plan
    )
    if bundle is None:
        raise Http404("Category not found.")
    paginator = Paginator(bundle["articles"], 12)
    page = paginator.get_page(request.GET.get("page"))
    return render(
        request,
        "marketing/kb_category_public.html",
        {
            "category": bundle["category"],
            "article_count": bundle["article_count"],
            "page_obj": page,
            "search_url": reverse("marketing_kb_search"),
        },
    )


@require_GET
def marketing_kb_article_view(request, article_slug: str):
    country, plan = _marketing_kb_region(request)
    article = marketing_kb_article_by_slug(
        article_slug, country_code=country, plan_tier=plan
    )
    if article is None:
        raise Http404("Article not found.")
    category_url = None
    if article.category_id and article.category:
        try:
            category_url = reverse(
                "marketing_kb_category",
                kwargs={"category_slug": article.category.slug},
            )
        except Exception:
            category_url = None
    return render(
        request,
        "marketing/kb_article_public.html",
        {
            "article": article,
            "search_url": reverse("marketing_kb_search"),
            "category_url": category_url,
        },
    )


@require_GET
def marketing_kb_typeahead_api(request):
    q = (request.GET.get("q") or "").strip()
    country, plan = _marketing_kb_region(request)
    suggestions = marketing_kb_typeahead(q, country_code=country, plan_tier=plan, limit=8)
    for row in suggestions:
        row["url"] = reverse("marketing_kb_article", kwargs={"article_slug": row["slug"]})
    return JsonResponse({"success": True, "query": q, "suggestions": suggestions})
