"""
Help north-star executive metrics bundle (batch 1349).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.db.models import Avg, Count
from django.utils import timezone


def build_north_star_bundle(*, days: int = 30) -> dict[str, Any]:
    since = timezone.now() - timedelta(days=days)
    bundle: dict[str, Any] = {"days": days, "generated_at": timezone.now().isoformat()}

    try:
        from apps.portal.help_search_intelligence import (
            deflection_rate_summary,
            zero_result_fingerprints,
        )

        bundle["deflection"] = deflection_rate_summary(days=days)
        bundle["zero_results"] = zero_result_fingerprints(days=days, limit=15)
    except Exception:
        bundle["deflection"] = {}
        bundle["zero_results"] = []

    try:
        from apps.feedback.models import (
            HelpSearchQueryLog,
            SupportAIInteractionReview,
            SupportAISessionRating,
            SupportDeflectionEvent,
        )

        # tenant-isolation-allow: operator-help-north-star-cross-tenant-fingerprint-aggregate
        bundle["searches"] = HelpSearchQueryLog.objects.filter(
            created_at__gte=since
        ).count()
        # tenant-isolation-allow: operator-help-north-star-cross-tenant-fingerprint-aggregate
        bundle["deflection_events"] = SupportDeflectionEvent.objects.filter(
            created_at__gte=since
        ).count()
        # tenant-isolation-allow: operator-help-north-star-cross-tenant-fingerprint-aggregate
        bundle["ai_reviews_pending"] = SupportAIInteractionReview.objects.filter(
            status=SupportAIInteractionReview.Status.PENDING
        ).count()
        # tenant-isolation-allow: operator-help-north-star-cross-tenant-fingerprint-aggregate
        ratings = SupportAISessionRating.objects.filter(created_at__gte=since)
        bundle["ai_csat_count"] = ratings.count()
        pos = ratings.filter(thumbs="up").count()
        neg = ratings.filter(thumbs="down").count()
        bundle["ai_csat_positive_pct"] = (
            round(100.0 * pos / (pos + neg), 1) if (pos + neg) else None
        )
        bundle["ai_csat_avg_stars"] = ratings.aggregate(avg=Avg("stars"))["avg"]
    except Exception:
        pass

    try:
        from apps.portal.models_kb import KBArticle

        # tenant-isolation-allow: operator-help-north-star-global-kb-inventory-counts
        bundle["kb_published"] = KBArticle.objects.filter(status="PUBLISHED").count()
        # tenant-isolation-allow: operator-help-north-star-global-kb-inventory-counts
        bundle["kb_drafts"] = KBArticle.objects.filter(status="DRAFT").count()
        if hasattr(KBArticle, "locale_group_id"):
            bundle["kb_translation_groups"] = (
                # tenant-isolation-allow: operator-help-north-star-global-kb-inventory-counts
                KBArticle.objects.exclude(locale_group_id="")
                .values("locale_group_id")
                .annotate(n=Count("id"))
                .count()
            )
    except Exception:
        pass

    return bundle
