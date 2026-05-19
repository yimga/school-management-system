"""Partner dashboard metrics aggregations.

Per-publisher views of installs, MRR, churn, payouts, and webhook health.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.utils import timezone

from apps.marketplace.models import (
    AppInstallation,
    MarketplaceApp,
    PlatformMarketplaceEarning,
    PublisherOrganization,
    TenantMarketplaceSubscription,
    WebhookDelivery,
    WebhookEndpoint,
)


def metrics_for_publisher(publisher: PublisherOrganization) -> dict:
    """Aggregate top-line metrics. Cheap counts/sums, suitable for a dashboard hit."""

    app_ids = list(MarketplaceApp.objects.filter(publisher=publisher).values_list("id", flat=True))
    if not app_ids:
        return {
            "app_count": 0,
            "installs_active": 0,
            "installs_lifetime": 0,
            "mrr_cents": 0,
            "mrr_currency": "USD",
            "publisher_share_30d": Decimal("0.00"),
            "publisher_share_lifetime": Decimal("0.00"),
            "churn_30d_pct": 0.0,
            "webhook_health": {"endpoints": 0, "succeeded": 0, "failed": 0, "abandoned": 0},
        }

    install_counts = AppInstallation.objects.filter(app_id__in=app_ids).aggregate(  # tenant-isolation-allow: marketplace-partner-install-metrics-aggregate
        active=Count("id", filter=Q(status=AppInstallation.Status.ACTIVE)),
        lifetime=Count("id"),
        uninstalled_30d=Count(
            "id",
            filter=Q(
                status=AppInstallation.Status.UNINSTALLED,
                uninstalled_at__gte=timezone.now() - timedelta(days=30),
            ),
        ),
    )

    subs = TenantMarketplaceSubscription.objects.filter(  # tenant-isolation-allow: marketplace-partner-subscription-metrics-aggregate
        app_id__in=app_ids, status=TenantMarketplaceSubscription.Status.ACTIVE
    )
    mrr_cents = 0
    for s in subs.values("unit_amount", "billing_interval"):
        amt = s["unit_amount"] or Decimal("0")
        interval = (s["billing_interval"] or "").lower()
        if interval == "monthly":
            mrr_cents += int(amt * 100)
        elif interval == "annual":
            mrr_cents += int((amt / Decimal("12")) * 100)
        # one-time / none -> 0 MRR contribution

    earnings = PlatformMarketplaceEarning.objects.filter(app_id__in=app_ids)  # tenant-isolation-allow: marketplace-partner-earnings-metrics-aggregate
    pub_share_30d = earnings.filter(
        recorded_at__gte=timezone.now() - timedelta(days=30)
    ).aggregate(s=Sum("publisher_share_amount"))["s"] or Decimal("0.00")
    pub_share_lifetime = earnings.aggregate(s=Sum("publisher_share_amount"))["s"] or Decimal("0.00")

    # Webhook health: last 24h
    wh_24h = WebhookDelivery.objects.filter(  # tenant-isolation-allow: marketplace-partner-webhook-metrics-aggregate
        app_id__in=app_ids, created_at__gte=timezone.now() - timedelta(hours=24)
    ).aggregate(
        succeeded=Count("id", filter=Q(status=WebhookDelivery.Status.SUCCEEDED)),
        failed=Count("id", filter=Q(status=WebhookDelivery.Status.FAILED)),
        abandoned=Count("id", filter=Q(status=WebhookDelivery.Status.ABANDONED)),
    )
    endpoints = WebhookEndpoint.objects.filter(app_id__in=app_ids, is_active=True).count()

    # Churn: uninstalls_30d / max(active+uninstalled_30d, 1).
    active = install_counts["active"] or 0
    uninstalled_30d = install_counts["uninstalled_30d"] or 0
    denom = active + uninstalled_30d
    churn_30d_pct = (uninstalled_30d / denom * 100.0) if denom else 0.0

    return {
        "app_count": len(app_ids),
        "installs_active": active,
        "installs_lifetime": install_counts["lifetime"] or 0,
        "mrr_cents": mrr_cents,
        "mrr_currency": "USD",
        "publisher_share_30d": pub_share_30d,
        "publisher_share_lifetime": pub_share_lifetime,
        "churn_30d_pct": round(churn_30d_pct, 2),
        "webhook_health": {
            "endpoints": endpoints,
            "succeeded": wh_24h["succeeded"] or 0,
            "failed": wh_24h["failed"] or 0,
            "abandoned": wh_24h["abandoned"] or 0,
        },
    }


def per_app_metrics(publisher: PublisherOrganization) -> list[dict]:
    rows = []
    apps = (
        MarketplaceApp.objects.filter(publisher=publisher)
        .select_related("listing")
        .order_by("name")
    )
    for app in apps:
        install_counts = AppInstallation.objects.filter(app=app).aggregate(  # tenant-isolation-allow: marketplace-partner-install-rollups-by-publisher
            active=Count("id", filter=Q(status=AppInstallation.Status.ACTIVE)),
            lifetime=Count("id"),
            uninstalled_30d=Count(
                "id",
                filter=Q(
                    status=AppInstallation.Status.UNINSTALLED,
                    uninstalled_at__gte=timezone.now() - timedelta(days=30),
                ),
            ),
        )
        pub_share_30d = (
            PlatformMarketplaceEarning.objects.filter(  # tenant-isolation-allow: marketplace-partner-earnings-rollups-by-publisher
                app=app, recorded_at__gte=timezone.now() - timedelta(days=30)
            ).aggregate(s=Sum("publisher_share_amount"))["s"]
            or Decimal("0.00")
        )
        rows.append(
            {
                "app": app,
                "active_installs": install_counts["active"] or 0,
                "lifetime_installs": install_counts["lifetime"] or 0,
                "uninstalled_30d": install_counts["uninstalled_30d"] or 0,
                "publisher_share_30d": pub_share_30d,
            }
        )
    return rows
