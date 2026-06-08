"""Offline KB article pack for local-first read mirror (batch 1650)."""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from apps.portal.kb_context import filter_kb_articles_by_school, filter_kb_articles_for_host, published_kb_queryset
from apps.portal.kb_office_service import is_operator_help_request


def _offline_enabled_for_request(request) -> bool:
    site = getattr(request, "site", None)
    runtime = (
        site.get_offline_runtime_settings()
        if site is not None and callable(getattr(site, "get_offline_runtime_settings", None))
        else {"enable_offline_mode": bool(getattr(site, "enable_offline_mode", True))}
    )
    return bool(runtime.get("enable_offline_mode", True))


@login_required
@require_GET
def api_kb_offline_pack(request):
    """Return published KB articles for Dexie hydrate (LibreOffice offline read path)."""
    if not _offline_enabled_for_request(request):
        return JsonResponse({"results": [], "disabled": True})

    is_op = is_operator_help_request(request)
    qs = published_kb_queryset()
    qs = filter_kb_articles_for_host(qs, is_operator=is_op)
    qs = filter_kb_articles_by_school(qs, request)
    qs = qs.order_by("-updated_at")[:80]

    results: list[dict] = []
    for article in qs:
        slug = getattr(article, "slug", "") or ""
        if not slug:
            continue
        results.append(
            {
                "id": str(article.pk),
                "slug": slug,
                "title": (article.title or "")[:240],
                "summary": (article.summary or "")[:400],
                "content": (article.content or "")[:12000],
                "locale": getattr(article, "locale", "") or "en",
                "locale_group_id": getattr(article, "locale_group_id", "") or "",
                "updated_at": (
                    article.updated_at.isoformat()
                    if getattr(article, "updated_at", None)
                    else ""
                ),
                "has_odt": bool(getattr(article, "odt_file", None)),
            }
        )

    return JsonResponse(
        {
            "results": results,
            "count": len(results),
            "operator_surface": is_op,
        }
    )
