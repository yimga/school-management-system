"""
Grant lifecycle services (Wedge 5): drive a GrantApplication through draft →
submitted → under_review → awarded/declined → closed, plus renewals. On award the
grant credits a finance ``AwardSource`` via ``aid_services.credit_award_source``
(idempotent, posts to the GL + writes an audit row) rather than forking a funding
ledger. Imports are lazy to avoid app-load cycles.
"""

from __future__ import annotations

import logging
from decimal import Decimal, InvalidOperation
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


def submit_grant(grant) -> dict[str, Any]:
    from apps.schools.models import GrantApplication

    if grant.status != GrantApplication.Status.DRAFT:
        return {"ok": False, "error": "Only a draft application can be submitted."}
    grant.status = GrantApplication.Status.SUBMITTED
    grant.submitted_at = timezone.now()
    grant.save(update_fields=["status", "submitted_at", "updated_at"])
    return {"ok": True, "status": grant.status}


def mark_under_review(grant) -> dict[str, Any]:
    from apps.schools.models import GrantApplication

    if grant.status != GrantApplication.Status.SUBMITTED:
        return {"ok": False, "error": "Only a submitted application can move to review."}
    grant.status = GrantApplication.Status.UNDER_REVIEW
    grant.save(update_fields=["status", "updated_at"])
    return {"ok": True, "status": grant.status}


def decline_grant(grant, *, reason: str = "") -> dict[str, Any]:
    from apps.schools.models import GrantApplication

    if grant.status in (
        GrantApplication.Status.AWARDED,
        GrantApplication.Status.CLOSED,
    ):
        return {"ok": False, "error": "An awarded or closed grant cannot be declined."}
    grant.status = GrantApplication.Status.DECLINED
    grant.decided_at = timezone.now()
    if reason:
        grant.notes = f"{grant.notes}\nDeclined: {reason}".strip()[:4000]  # magic-number-allow: free-text notes truncation cap
    grant.save(update_fields=["status", "decided_at", "notes", "updated_at"])
    return {"ok": True, "status": grant.status}


def award_grant(
    grant, *, awarded_amount=None, award_source_id=None, user_id=None
) -> dict[str, Any]:
    """
    Mark a grant AWARDED for ``awarded_amount`` (defaults to requested_amount) and,
    when an AwardSource is supplied, credit that fund exactly once via the finance aid
    service (which posts to the GL + audit). Idempotent via ``credited_to_fund_at``.
    """
    from apps.schools.models import GrantApplication

    if grant.status == GrantApplication.Status.CLOSED:
        return {"ok": False, "error": "A closed grant cannot be re-awarded."}

    amount = grant.requested_amount if awarded_amount is None else awarded_amount
    try:
        amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return {"ok": False, "error": "Invalid awarded amount."}
    if amount <= 0:
        return {"ok": False, "error": "Awarded amount must be positive."}

    # Resolve + validate the fund BEFORE mutating grant state, so a bad source never
    # leaves the grant marked AWARDED-but-unfunded (which the idempotency guard would
    # then refuse to re-credit on a retry).
    source = None
    if award_source_id and grant.credited_to_fund_at is None:
        from apps.finance.models import AwardSource

        source = AwardSource.objects.filter(
            school_id=grant.school_id, pk=award_source_id
        ).first()
        if not source:
            return {"ok": False, "error": "Award source not found for this school."}

    grant.awarded_amount = amount
    grant.status = GrantApplication.Status.AWARDED
    grant.decided_at = grant.decided_at or timezone.now()
    fields = ["awarded_amount", "status", "decided_at", "updated_at"]

    credit_result = None
    if source is not None:
        from apps.finance.aid_services import credit_award_source

        credit_result = credit_award_source(
            school_id=grant.school_id,
            source_id=source.pk,
            amount=amount,
            currency=grant.currency,
            reason=f"Grant award: {grant.funder_name}",
            user_id=user_id,
        )
        if credit_result.get("ok"):
            grant.award_source = source
            grant.credited_to_fund_at = timezone.now()
            fields += ["award_source", "credited_to_fund_at"]

    grant.save(update_fields=fields)
    return {
        "ok": True,
        "status": grant.status,
        "awarded_amount": amount,
        "credit": credit_result,
    }


def close_grant(grant) -> dict[str, Any]:
    """Close out an awarded grant once every milestone is completed or waived."""
    from apps.schools.models import GrantApplication, GrantMilestone

    if grant.status != GrantApplication.Status.AWARDED:
        return {"ok": False, "error": "Only an awarded grant can be closed out."}
    open_milestones = grant.milestones.exclude(
        status__in=(GrantMilestone.Status.COMPLETED, GrantMilestone.Status.WAIVED)
    ).count()
    if open_milestones:
        return {"ok": False, "error": f"{open_milestones} milestone(s) still pending."}
    grant.status = GrantApplication.Status.CLOSED
    grant.save(update_fields=["status", "updated_at"])
    return {"ok": True, "status": grant.status}


def open_grant_renewal(grant) -> dict[str, Any]:
    """Create a fresh DRAFT application that renews a closed/awarded grant."""
    from apps.schools.models import GrantApplication

    if grant.status not in (
        GrantApplication.Status.AWARDED,
        GrantApplication.Status.CLOSED,
    ):
        return {"ok": False, "error": "Only an awarded or closed grant can be renewed."}
    renewal = GrantApplication.objects.create(
        school_id=grant.school_id,
        funder_name=grant.funder_name,
        program=grant.program,
        requested_amount=grant.awarded_amount or grant.requested_amount,
        currency=grant.currency,
        narrative=grant.narrative,
        renewed_from=grant,
    )
    return {"ok": True, "renewal_id": renewal.pk}
