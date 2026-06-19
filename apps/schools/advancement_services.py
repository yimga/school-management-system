"""
Advancement (Wedge 5) services that connect donor gifts to the finance aid funds
and in-kind donations to the schoolops inventory register.

These are deliberately thin adapters: monetary crediting lives in
``apps.finance.aid_services`` (it owns AwardSource/AidAuditLog) and inventory lives in
``apps.schoolops.models``. Imports are lazy to avoid app-load cycles.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


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


def reject_in_kind_donation(donation, *, reason: str = "") -> dict:
    """Mark an in-kind donation rejected. An accepted donation cannot be rejected."""
    if donation.status == donation.Status.ACCEPTED:
        return {"ok": False, "error": "Cannot reject an accepted donation"}
    donation.status = donation.Status.REJECTED
    if reason:
        donation.notes = f"{donation.notes}\nRejected: {reason}".strip()[:2000]
    donation.save(update_fields=["status", "notes", "updated_at"])
    return {"ok": True}
