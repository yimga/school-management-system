"""
Operator cross-tenant funding overview (platform-wide advancement rollup).

Read-only aggregation across ALL tenants for platform operators: total cash
raised, gifts, accepted in-kind value, outstanding pledges, active campaigns, plus
a per-school leaderboard with each tenant's advancement on/off status. Reuses the
existing ``platform.tenant.read`` scope — no new operator scope, no migration.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Sum
from django.shortcuts import render
from django.views.decorators.http import require_GET

from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_TENANT_READ,
    require_platform_scope,
)

from .advancement_services import advancement_enabled
from .models import (
    AdvancementGift,
    DonationPledge,
    FundraisingCampaign,
    InKindDonation,
    School,
)

_ALLOW = "operator-cross-tenant-funding-rollup-reviewed-2026-06-20"


@require_GET
@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_funding_overview(request):
    """Platform-wide funding rollup across all tenants (operator, read-only)."""
    gift_agg = AdvancementGift.objects.aggregate(  # tenant-isolation-allow: operator-cross-tenant-funding-rollup-reviewed-2026-06-20
        total=Sum("amount"), n=Count("id")
    )
    in_kind_agg = InKindDonation.objects.filter(  # tenant-isolation-allow: operator-cross-tenant-funding-rollup-reviewed-2026-06-20
        status=InKindDonation.Status.ACCEPTED
    ).aggregate(total=Sum("estimated_value"), n=Count("id"))
    pledge_agg = DonationPledge.objects.filter(  # tenant-isolation-allow: operator-cross-tenant-funding-rollup-reviewed-2026-06-20
        status__in=(DonationPledge.Status.PLEDGED, DonationPledge.Status.PARTIAL)
    ).aggregate(amt=Sum("amount"), ful=Sum("fulfilled_amount"), n=Count("id"))
    active_campaigns = FundraisingCampaign.objects.filter(  # tenant-isolation-allow: operator-cross-tenant-funding-rollup-reviewed-2026-06-20
        status=FundraisingCampaign.Status.ACTIVE
    ).count()

    pledged_outstanding = (pledge_agg["amt"] or Decimal("0.00")) - (
        pledge_agg["ful"] or Decimal("0.00")
    )

    per_school = list(
        AdvancementGift.objects.values(  # tenant-isolation-allow: operator-cross-tenant-funding-rollup-reviewed-2026-06-20
            "donor__school_id", "donor__school__name"
        )
        .annotate(raised=Sum("amount"), gifts=Count("id"))
        .order_by("-raised")[:50]
    )
    school_ids = [r["donor__school_id"] for r in per_school]
    schools_by_id = {s.pk: s for s in School.objects.filter(pk__in=school_ids)}
    rows = [
        {
            "school_id": r["donor__school_id"],
            "name": r["donor__school__name"],
            "raised": r["raised"] or Decimal("0.00"),
            "gifts": r["gifts"],
            "advancement_enabled": advancement_enabled(
                schools_by_id.get(r["donor__school_id"])
            ),
        }
        for r in per_school
    ]

    context = {
        "total_cash_raised": gift_agg["total"] or Decimal("0.00"),
        "gift_count": gift_agg["n"] or 0,
        "in_kind_accepted_value": in_kind_agg["total"] or Decimal("0.00"),
        "in_kind_accepted_count": in_kind_agg["n"] or 0,
        "pledged_outstanding": pledged_outstanding,
        "open_pledge_count": pledge_agg["n"] or 0,
        "active_campaigns": active_campaigns,
        "rows": rows,
        "tenant_count": len(rows),
    }
    return render(request, "schools/super/funding_overview.html", context)
