"""
Public donor portal (Wedge 5): a donor opens a signed magic-link to view their
own gifts, receipts, and the school's public campaigns. NO login — the UUID token
is the credential; the school is resolved from the token's donor FK, not the host.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from .advancement_services import resolve_donor_access_link
from .models import FundraisingCampaign


@require_http_methods(["GET"])
def donor_portal(request, token):
    link = resolve_donor_access_link(token)
    if not link:
        return render(request, "donors/donor_link_invalid.html", status=400)

    donor = link.donor
    school = donor.school
    gifts = list(donor.gifts.select_related("campaign").all()[:200])
    in_kind = list(donor.in_kind_donations.all()[:200])
    total_given = donor.gifts.aggregate(total=Sum("amount"))["total"] or Decimal("0.00")
    public_campaigns = list(
        FundraisingCampaign.objects.filter(school=school, is_public=True)
        .exclude(status=FundraisingCampaign.Status.CANCELLED)
        .order_by("-created_at")[:25]
    )
    return render(
        request,
        "donors/donor_portal.html",
        {
            "donor": donor,
            "school": school,
            "gifts": gifts,
            "in_kind": in_kind,
            "total_given": total_given,
            "public_campaigns": public_campaigns,
        },
    )
