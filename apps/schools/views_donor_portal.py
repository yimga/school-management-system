"""
Public donor portal (Wedge 5): a donor opens a signed magic-link to view their
own gifts, receipts, and the school's public campaigns. NO login — the UUID token
is the credential; the school is resolved from the token's donor FK, not the host.
"""

from __future__ import annotations

from decimal import Decimal

from django.db.models import Sum
from django.http import Http404
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
            "token": link.token,
            "gifts": gifts,
            "in_kind": in_kind,
            "total_given": total_given,
            "public_campaigns": public_campaigns,
        },
    )


@require_http_methods(["GET"])
def donor_receipt_pdf(request, token, gift_id):
    """
    Public tax-receipt PDF for a single gift. Same magic-link credential as the
    portal: the gift is looked up ONLY within the token's own donor, so a leaked
    token can never fetch another donor's receipt. Degrades to an HTML receipt
    when WeasyPrint's system libraries are unavailable, so the donor always gets
    something printable.
    """
    from apps.reports.weasy import render_pdf

    link = resolve_donor_access_link(token)
    if not link:
        return render(request, "donors/donor_link_invalid.html", status=400)

    donor = link.donor
    gift = (
        donor.gifts.select_related("campaign", "award_source")
        .filter(pk=gift_id)
        .first()
    )
    if gift is None:
        raise Http404("Gift not found for this donor.")

    school = donor.school
    receipt_reference = f"DR-{gift.received_at:%Y}-{gift.pk}"
    context = {
        "donor": donor,
        "gift": gift,
        "school": school,
        "logo_url": school.logo_url or "",
        "primary_color": getattr(school, "primary_color", "") or "",
        "receipt_reference": receipt_reference,
    }
    filename = f"donation-receipt-{receipt_reference}.pdf"
    try:
        response = render_pdf(request, "donors/gift_receipt.html", context, filename=filename)
    except RuntimeError:
        # WeasyPrint deps absent in this environment — degrade to the HTML receipt
        # (same template) rather than 500. Still a printable, delivered record for the
        # donor, so it counts as a sent receipt just like the PDF path below.
        response = render(request, "donors/gift_receipt.html", context)

    # A receipt was generated and delivered (PDF or HTML fallback), so the
    # previously-dormant receipt_sent flag now becomes meaningful. Scoped update
    # keeps it idempotent and race-free.
    if not gift.receipt_sent:
        donor.gifts.filter(pk=gift.pk).update(receipt_sent=True)
    return response
