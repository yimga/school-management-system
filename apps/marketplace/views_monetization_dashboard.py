"""
Tenant marketplace monetization dashboard (school-scoped aggregates; no secrets).
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.db.models import Count, Sum
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET

from apps.marketplace.models import AppInstallation, MarketplaceMonetizationLedgerEntry
from apps.marketplace.permissions import tenant_marketplace_manage_required
from apps.marketplace.settlement_truth import blocked_settlement_reason_from_entry


@login_required
@tenant_marketplace_manage_required
@require_GET
def monetization_dashboard(request):
    school = getattr(request, "school", None)
    if not school:
        return render(
            request,
            "marketplace/monetization_dashboard.html",
            {
                "school": None,
                "page_title": "Marketplace monetization",
                "rows": [],
                "totals": {},
                "sku_usage": [],
                "ledger_summary": {},
                "install_mix": {},
                "primary_action_url": None,
                "primary_action_label": None,
                "settlement_note": "",
                "settlement_blocked_detail": "",
            },
        )

    qs = MarketplaceMonetizationLedgerEntry.objects.filter(school=school)
    by_event = dict(
        qs.values("event_type")
        .annotate(n=Count("id"))
        .values_list("event_type", "n")
    )
    fees = qs.filter(
        event_type=MarketplaceMonetizationLedgerEntry.EventType.PLATFORM_FEE_RECORDED
    ).aggregate(s=Sum("platform_fee_amount"))
    gross_usage = qs.filter(
        event_type=MarketplaceMonetizationLedgerEntry.EventType.PAYMENT_SUCCESS
    ).aggregate(s=Sum("amount"))

    pending_ext = int(
        by_event.get(
            MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_PENDING_EXTERNAL,
            0,
        )
        or 0
    )
    blocked = int(
        by_event.get(
            MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_EXTERNAL_BLOCKED,
            0,
        )
        or 0
    )
    completed = int(
        by_event.get(
            MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_COMPLETED,
            0,
        )
        or 0
    )

    sku_rows = list(
        qs.exclude(sku_key="")
        .values("sku_key")
        .annotate(n=Count("id"), amt=Sum("amount"))
        .order_by("-n")[:12]
    )

    paid_installs = AppInstallation.objects.filter(
        school=school,
        status=AppInstallation.Status.ACTIVE,
        uninstalled_at__isnull=True,
        app__pricing_model__in=["subscription", "usage"],
    ).count()
    free_installs = AppInstallation.objects.filter(
        school=school,
        status=AppInstallation.Status.ACTIVE,
        uninstalled_at__isnull=True,
        app__pricing_model="free",
    ).count()

    primary_url = None
    primary_label = None
    if blocked > 0 or pending_ext > 0:
        try:
            primary_url = reverse("finance:payment_readiness_setup")
            primary_label = "Review payment readiness"
        except NoReverseMatch:
            primary_url = reverse("tenant_app_catalog")
            primary_label = "Back to marketplace catalog"

    blocked_entry = (
        qs.filter(
            event_type=MarketplaceMonetizationLedgerEntry.EventType.SETTLEMENT_EXTERNAL_BLOCKED
        )
        .order_by("-created_at")
        .first()
    )
    settlement_blocked_detail = blocked_settlement_reason_from_entry(blocked_entry)

    settlement_note = ""
    if blocked > 0:
        settlement_note = (
            "Some settlements are blocked until regional payment readiness and PSP "
            "customer setup are complete. This is expected when live rails are not configured."
        )
    elif pending_ext > 0 and completed == 0:
        settlement_note = (
            "Settlement rows may remain pending until processor webhooks confirm funds "
            "(test and relay processors never claim live production settlement)."
        )

    return render(
        request,
        "marketplace/monetization_dashboard.html",
        {
            "school": school,
            "page_title": "Marketplace monetization",
            "ledger_summary": {
                "by_event": by_event,
                "platform_fees_sum": str(fees.get("s") or Decimal("0.00")),
                "payment_success_sum": str(gross_usage.get("s") or Decimal("0.00")),
                "pending_external_events": pending_ext,
                "blocked_events": blocked,
                "completed_settlement_events": completed,
            },
            "sku_usage": sku_rows,
            "install_mix": {"paid_installations": paid_installs, "free_installations": free_installs},
            "primary_action_url": primary_url,
            "primary_action_label": primary_label,
            "settlement_note": settlement_note,
            "settlement_blocked_detail": settlement_blocked_detail,
        },
    )
