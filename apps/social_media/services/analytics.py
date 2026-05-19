"""Per-tenant social engagement metrics for dashboard charts."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.db.models import Count, Sum
from django.utils import timezone

from apps.social_media.models import SocialCampaignAttribution, SocialMediaIntegration


def pulse_timeseries_for_school(school_id, *, days: int = 14) -> list[dict[str, Any]]:
    """
    Build ``PulseTimeseriesPoint``-compatible rows for ``PlatformPulseLineChart``.

    ``attendanceRate`` carries normalized impression index; ``revenue`` carries
    attributed donation cents (scaled down for chart readability).
    """
    since = timezone.now() - timedelta(days=days)
    attributions = (
        SocialCampaignAttribution.objects.filter(school_id=school_id, recorded_at__gte=since)
        .values("recorded_at__date")
        .annotate(total_cents=Sum("amount_cents"), hits=Count("id"))
    )
    by_date: dict[str, dict[str, float]] = defaultdict(lambda: {"revenue": 0.0, "hits": 0.0})
    for row in attributions:
        d = str(row["recorded_at__date"])
        by_date[d]["revenue"] = float(row["total_cents"] or 0) / 100.0
        by_date[d]["hits"] = float(row["hits"] or 0)

    integrations = SocialMediaIntegration.objects.filter(school_id=school_id, is_active=True)
    impression_proxy = 0.0
    for integration in integrations:
        impression_proxy += float(len(integration.feed_cache_json or []))

    points: list[dict[str, Any]] = []
    for offset in range(days):
        day = (timezone.now() - timedelta(days=days - 1 - offset)).date()
        key = str(day)
        bucket = by_date.get(key, {"revenue": 0.0, "hits": 0.0})
        rate = min(100.0, (bucket["hits"] / max(1.0, impression_proxy)) * 100.0) if impression_proxy else 0.0
        points.append(
            {
                "date": key,
                "attendanceRate": round(rate, 2),
                "revenue": round(bucket["revenue"], 2),
            }
        )
    return points


def record_utm_attribution(
    *,
    school_id,
    provider: str,
    utm_source: str,
    utm_medium: str,
    utm_campaign: str,
    amount_cents: int = 0,
    transaction_id: str = "",
    post_id: str = "",
) -> SocialCampaignAttribution:
    return SocialCampaignAttribution.objects.create(
        school_id=school_id,
        provider=provider,
        utm_source=utm_source,
        utm_medium=utm_medium,
        utm_campaign=utm_campaign,
        amount_cents=amount_cents,
        transaction_id=transaction_id,
        post_id=post_id,
    )
