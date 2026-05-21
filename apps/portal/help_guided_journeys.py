"""
Guided help journeys — route prefix → KB article slugs (batch 1353).
"""

from __future__ import annotations

from typing import Any

# Prefix → ordered article slugs (tenant KB; operator uses manager help hub).
JOURNEY_BY_PREFIX: dict[str, list[str]] = {
    "/finance/": ["finance-dashboard", "payment-receipts", "fee-collection"],
    "/payroll/": ["payroll-overview", "payroll-runs"],
    "/evals/": ["gradebook-basics", "report-cards"],
    "/compliance/": ["compliance-checklist"],
    "/analytics/": ["analytics-dashboard"],
    "/feedback/": ["help-center-overview", "submit-feedback"],
    "/authentication/backend/": ["admin-dashboard", "user-roles"],
    "/studio/launch/": ["help-center-overview", "admin-dashboard"],
    "/studio/experience/": ["help-center-overview"],
    "/studio/automation/": ["help-center-overview"],
    "/studio/output/": ["report-cards", "help-center-overview"],
    "/studio/control/": ["help-center-overview", "admin-dashboard"],
    "/studio/": ["help-center-overview", "admin-dashboard"],
}


def journey_for_path(path: str, *, operator: bool = False) -> dict[str, Any] | None:
    p = (path or "").lower()
    for prefix, slugs in JOURNEY_BY_PREFIX.items():
        if p.startswith(prefix):
            return {
                "prefix": prefix,
                "slug_candidates": slugs,
                "operator": operator,
                "step_count": len(slugs),
            }
    return None


def resolve_journey_articles(
    *,
    school: Any,
    path: str,
    operator: bool = False,
    limit: int = 5,
) -> list[dict[str, Any]]:
    spec = journey_for_path(path, operator=operator)
    if not spec:
        return []
    try:
        from apps.portal.kb_context import filter_kb_articles_by_school, published_kb_queryset

        from apps.portal.kb_embeddings import filter_kb_queryset_by_locale_with_fallback

        qs = published_kb_queryset().filter(slug__in=spec["slug_candidates"])
        qs = filter_kb_articles_by_school(qs, school)
        qs = filter_kb_queryset_by_locale_with_fallback(qs)
        rows = list(qs[:limit])
        out: list[dict[str, Any]] = []
        for art in rows:
            try:
                from django.urls import reverse

                url = reverse("kb:kb_article", kwargs={"article_slug": art.slug})
            except Exception:
                url = ""
            out.append(
                {
                    "slug": art.slug,
                    "title": art.title,
                    "summary": (art.summary or "")[:200],
                    "url": url,
                }
            )
        return out
    except Exception:
        return []
