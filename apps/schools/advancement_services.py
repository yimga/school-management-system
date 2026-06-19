"""
Advancement (Wedge 5) services that connect donor gifts to the finance aid funds
and in-kind donations to the schoolops inventory register.

These are deliberately thin adapters: monetary crediting lives in
``apps.finance.aid_services`` (it owns AwardSource/AidAuditLog) and inventory lives in
``apps.schoolops.models``. Imports are lazy to avoid app-load cycles.
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.db import DatabaseError, transaction
from django.db.models import Count, Sum
from django.utils import timezone

logger = logging.getLogger(__name__)


def _as_decimal(value: Any) -> Decimal:
    if value is None:
        return Decimal("0.00")
    if isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (ArithmeticError, TypeError, ValueError):
        return Decimal("0.00")


def campaign_progress(campaign) -> dict[str, Any]:
    """
    Aggregate a campaign's progress from its linked gifts (money) and in-kind
    donations (estimated value). No stored running total — always computed.
    """
    gift_agg = campaign.gifts.aggregate(total=Sum("amount"), n=Count("id"))
    in_kind_agg = campaign.in_kind_donations.aggregate(
        total=Sum("estimated_value"), n=Count("id")
    )
    cash_raised = _as_decimal(gift_agg["total"])
    in_kind_value = _as_decimal(in_kind_agg["total"])
    raised = cash_raised + in_kind_value
    goal = _as_decimal(campaign.goal_amount)
    pct = int((raised / goal * 100).to_integral_value()) if goal > 0 else 0
    return {
        "id": campaign.pk,
        "name": campaign.name,
        "status": campaign.status,
        "currency": campaign.currency,
        "goal_amount": goal,
        "cash_raised": cash_raised,
        "in_kind_value": in_kind_value,
        "raised": raised,
        "pct_to_goal": min(pct, 100),
        "over_goal": raised > goal > 0,
        "gift_count": gift_agg["n"] or 0,
        "in_kind_count": in_kind_agg["n"] or 0,
        "is_public": campaign.is_public,
    }


def donations_overview(school_id: Any) -> dict[str, Any]:
    """
    Tenant donations dashboard summary: campaign progress, gift/in-kind totals,
    pending in-kind acceptances, and (best-effort) the aid endowment health report.
    All tenant-scoped by school_id.
    """
    from apps.finance.aid_services import get_endowment_health_report
    from apps.schools.models import (
        AdvancementGift,
        FundraisingCampaign,
        InKindDonation,
    )

    campaigns = [
        campaign_progress(c)
        for c in FundraisingCampaign.objects.filter(school_id=school_id).exclude(
            status=FundraisingCampaign.Status.CANCELLED
        )[:50]
    ]
    gift_agg = AdvancementGift.objects.filter(donor__school_id=school_id).aggregate(
        total=Sum("amount"), n=Count("id")
    )
    credited_agg = AdvancementGift.objects.filter(
        donor__school_id=school_id, credited_to_fund_at__isnull=False
    ).aggregate(total=Sum("amount"))
    in_kind_pending = InKindDonation.objects.filter(
        school_id=school_id, status=InKindDonation.Status.PENDING
    ).count()
    in_kind_accepted = InKindDonation.objects.filter(
        school_id=school_id, status=InKindDonation.Status.ACCEPTED
    ).aggregate(total=Sum("estimated_value"), n=Count("id"))

    endowment: list[dict] = []
    try:
        endowment = get_endowment_health_report(school_id)
    except (DatabaseError, ValueError, TypeError, ArithmeticError) as e:
        logger.debug("donations_overview endowment report skip: %s", e)

    return {
        "campaigns": campaigns,
        "total_cash_raised": _as_decimal(gift_agg["total"]),
        "gift_count": gift_agg["n"] or 0,
        "total_credited_to_funds": _as_decimal(credited_agg["total"]),
        "in_kind_pending": in_kind_pending,
        "in_kind_accepted_count": in_kind_accepted["n"] or 0,
        "in_kind_accepted_value": _as_decimal(in_kind_accepted["total"]),
        "endowment": endowment,
    }


def designate_and_credit_gift(
    gift, award_source_id: Any, *, user_id: int | None = None
) -> dict | None:
    """
    Link a gift to a school AwardSource and credit the fund exactly once.

    Returns the finance crediting result (``{"ok": ...}``), or ``None`` when no
    source is supplied or the gift was already credited. Idempotent via
    ``gift.credited_to_fund_at`` — a re-submit never double-credits.
    """
    if not award_source_id or gift.credited_to_fund_at is not None:
        return None
    from apps.finance.aid_services import credit_award_source
    from apps.finance.models import AwardSource

    source = AwardSource.objects.filter(
        school_id=gift.donor.school_id, pk=award_source_id
    ).first()
    if not source:
        return {"ok": False, "error": "Award source not found for this school."}

    reason = f"Donation from {gift.donor.display_name}"
    if gift.campaign_name:
        reason += f" — {gift.campaign_name}"

    result = credit_award_source(
        school_id=gift.donor.school_id,
        source_id=source.pk,
        amount=gift.amount,
        currency=gift.currency,
        reason=reason,
        user_id=user_id,
    )
    if result.get("ok"):
        gift.award_source = source
        gift.credited_to_fund_at = timezone.now()
        gift.save(update_fields=["award_source", "credited_to_fund_at"])
    return result


def accept_in_kind_donation(
    donation, *, location: str = "", user_id: int | None = None
) -> dict:
    """
    Accept an in-kind donation and land it in the schoolops inventory register —
    incrementing an existing same-named line for this school, or creating one.
    Idempotent: an already-accepted donation is not re-applied.
    """
    if donation.status == donation.Status.ACCEPTED:
        return {"ok": False, "error": "Already accepted"}

    from apps.schoolops.models import InventoryItem

    name = (donation.description or "").strip()[:255] or "In-kind donation"
    qty = max(1, int(donation.quantity or 1))
    with transaction.atomic():
        item = (
            InventoryItem.objects.filter(school_id=donation.school_id, name=name)
            .order_by("pk")
            .first()
        )
        if item:
            item.quantity = (item.quantity or 0) + qty
            if location and not item.location:
                item.location = location[:255]
            item.save(update_fields=["quantity", "location", "updated_at"])
        else:
            note = "In-kind donation"
            if donation.donor_id:
                note += f" from {donation.donor.display_name}"
            if donation.received_at:
                note += f" ({donation.received_at})"
            item = InventoryItem.objects.create(
                school_id=donation.school_id,
                name=name,
                quantity=qty,
                location=location[:255],
                notes=note,
            )
        donation.inventory_item = item
        donation.status = donation.Status.ACCEPTED
        donation.save(update_fields=["inventory_item", "status", "updated_at"])
    return {"ok": True, "inventory_item_id": item.pk, "quantity": item.quantity}


def mint_donor_access_link(donor, *, days: int = 30):
    """Create a fresh signed magic-link grant for a donor (default 30-day expiry)."""
    from datetime import timedelta

    from apps.schools.models import DonorGiftAccessLink

    days = max(1, min(int(days), 365))  # magic-number-allow: max-link-expiry-days
    return DonorGiftAccessLink.objects.create(
        donor=donor,
        expires_at=timezone.now() + timedelta(days=days),
    )


def resolve_donor_access_link(token):
    """
    Return a valid (unexpired) DonorGiftAccessLink for the token, bumping its
    access counters; or None. Token is the only credential — no login required.
    """
    from apps.schools.models import DonorGiftAccessLink

    link = (
        DonorGiftAccessLink.objects.select_related("donor", "donor__school")
        .filter(token=token, expires_at__gt=timezone.now())
        .first()
    )
    if not link:
        return None
    DonorGiftAccessLink.objects.filter(pk=link.pk).update(
        last_accessed_at=timezone.now(), access_count=link.access_count + 1
    )
    return link


def send_donor_portal_link(donor, absolute_url: str) -> dict:
    """
    Email a donor their magic-link portal URL. Best-effort: returns the send
    result dict; never raises. Requires the donor to have an email.
    """
    if not (donor.email or "").strip():
        return {"ok": False, "error": "Donor has no email on file."}
    school = donor.school
    subject = f"Your giving summary — {school.name}"
    body = (
        f"Dear {donor.display_name},\n\n"
        f"You can view your gifts and receipts for {school.name} here:\n"
        f"{absolute_url}\n\n"
        f"This link is private to you and expires in 30 days.\n\n"
        f"With gratitude,\n{school.name}"
    )
    try:
        from apps.communication.notification_service import send_email

        ok = send_email(
            to_addresses=[donor.email],
            subject=subject,
            body=body,
            school=school,
            fail_silently=True,
        )
        return {"ok": bool(ok)}
    except (ImportError, ValueError, TypeError) as e:
        logger.warning("send_donor_portal_link failed: %s", e)
        return {"ok": False, "error": "Email delivery unavailable."}


def reject_in_kind_donation(donation, *, reason: str = "") -> dict:
    """Mark an in-kind donation rejected. An accepted donation cannot be rejected."""
    if donation.status == donation.Status.ACCEPTED:
        return {"ok": False, "error": "Cannot reject an accepted donation"}
    donation.status = donation.Status.REJECTED
    if reason:
        donation.notes = f"{donation.notes}\nRejected: {reason}".strip()[:2000]
    donation.save(update_fields=["status", "notes", "updated_at"])
    return {"ok": True}
