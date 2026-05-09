"""Partner-app submission lifecycle: submit → review → approve / reject.

Wraps the existing ``MarketplaceListing`` + ``MarketplaceReview`` models with a
service surface third-party publishers (and the in-house governance team) can
call without touching ORM internals. All operations are tenant-aware,
audit-logged, and idempotent where possible.

Stages (mirrors ``docs/developer/PARTNER_APP_CERTIFICATION.md``):

1. ``submit_for_review(app, requested_by)`` — publisher requests promotion from
   draft → in-review. Creates a SECURITY review row + flips listing to PENDING
   review status. Idempotent — re-submitting an already-pending app is a no-op.
2. ``list_pending_for_governance()`` — queue view for the governance team.
3. ``approve_partner_submission(review, approved_by, notes)`` — governance
   marks the review APPROVED, flips listing security_review_status + status to
   APPROVED, records ``approved_at`` / ``approved_by``.
4. ``reject_partner_submission(review, rejected_by, notes, findings)`` —
   marks the review REJECTED with structured findings the publisher can act on;
   listing security_review_status becomes CHANGES_REQUIRED.
5. ``request_changes(review, reviewer, notes, findings)`` — soft reject with a
   change-list; publisher can re-submit.
"""

from __future__ import annotations

import logging
from typing import Any

from django.db import transaction
from django.utils import timezone

from .models import MarketplaceApp, MarketplaceListing, MarketplaceReview

logger = logging.getLogger(__name__)


def _log_partner_event(*, app=None, action: str = "", payload=None, actor=None) -> None:
    """Structured platform-level audit log for partner submissions.

    Distinct from ``AppAuditLog`` (tenant-scoped) — partner submissions happen
    at the publisher level before any school has installed the app.
    """
    actor_id = getattr(actor, "pk", None)
    app_slug = getattr(app, "slug", "") if app else ""
    logger.info(
        "marketplace.partner_event action=%s app=%s actor_id=%s payload=%s",
        action,
        app_slug,
        actor_id,
        payload or {},
    )


class PartnerSubmissionError(ValueError):
    """Raised when a submission step is invalid (e.g. listing missing)."""


def _ensure_listing(app: MarketplaceApp) -> MarketplaceListing:
    listing = MarketplaceListing.objects.filter(app=app).first()
    if listing is None:
        raise PartnerSubmissionError(
            f"App {app.slug!r} has no MarketplaceListing — create one before review."
        )
    return listing


@transaction.atomic
def submit_for_review(
    app: MarketplaceApp,
    *,
    requested_by=None,
    notes: str = "",
) -> MarketplaceReview:
    """Move a partner app from DRAFT to IN_REVIEW. Idempotent.

    Creates a SECURITY review row if none is currently open for this listing
    (i.e. no PENDING / IN_REVIEW row). Returns the open review.
    """
    listing = _ensure_listing(app)

    open_review = (
        MarketplaceReview.objects.filter(
            listing=listing,
            review_type=MarketplaceReview.ReviewType.SECURITY,
            status__in=(
                MarketplaceReview.Status.PENDING,
                MarketplaceReview.Status.IN_REVIEW,
            ),
        )
        .order_by("-requested_at")
        .first()
    )
    if open_review:
        return open_review

    listing.security_review_status = MarketplaceListing.ReviewStatus.PENDING
    listing.status = MarketplaceListing.Status.PENDING_REVIEW
    listing.save(update_fields=["security_review_status", "status", "updated_at"])

    review = MarketplaceReview.objects.create(
        listing=listing,
        review_type=MarketplaceReview.ReviewType.SECURITY,
        status=MarketplaceReview.Status.PENDING,
        requested_by=requested_by,
        app_version=app.version or "",
        notes=notes,
    )
    _log_partner_event(
        app=app,
        action="marketplace.partner_submit",
        payload={"listing_id": listing.pk, "review_id": review.pk, "version": app.version},
        actor=requested_by,
    )
    return review


def list_pending_for_governance() -> list[MarketplaceReview]:
    """Queue view: every open security review across all listings, oldest first."""
    return list(
        MarketplaceReview.objects.filter(
            review_type=MarketplaceReview.ReviewType.SECURITY,
            status__in=(
                MarketplaceReview.Status.PENDING,
                MarketplaceReview.Status.IN_REVIEW,
            ),
        ).select_related("listing", "listing__app").order_by("requested_at")
    )


@transaction.atomic
def approve_partner_submission(
    review: MarketplaceReview,
    *,
    approved_by=None,
    notes: str = "",
    findings: dict[str, Any] | None = None,
) -> MarketplaceReview:
    """Approve a partner submission. Flips listing to APPROVED + records approver."""
    if review.review_type != MarketplaceReview.ReviewType.SECURITY:
        raise PartnerSubmissionError(
            "Only SECURITY reviews can be approved via this service."
        )
    listing = review.listing
    review.mark_reviewed(
        status=MarketplaceReview.Status.APPROVED,
        reviewed_by=approved_by,
        notes=notes,
        findings_json=findings or {},
    )
    listing.security_review_status = MarketplaceListing.ReviewStatus.APPROVED
    listing.status = MarketplaceListing.Status.APPROVED
    listing.approved_at = timezone.now()
    listing.approved_by = approved_by
    listing.save(
        update_fields=[
            "security_review_status",
            "status",
            "approved_at",
            "approved_by",
            "updated_at",
        ]
    )
    _log_partner_event(
        app=listing.app,
        action="marketplace.partner_approve",
        payload={"listing_id": listing.pk, "review_id": review.pk, "notes": notes[:500]},
        actor=approved_by,
    )
    return review


@transaction.atomic
def reject_partner_submission(
    review: MarketplaceReview,
    *,
    rejected_by=None,
    notes: str = "",
    findings: dict[str, Any] | None = None,
) -> MarketplaceReview:
    """Hard reject. Listing security_review_status becomes REJECTED."""
    if review.review_type != MarketplaceReview.ReviewType.SECURITY:
        raise PartnerSubmissionError(
            "Only SECURITY reviews can be rejected via this service."
        )
    listing = review.listing
    review.mark_reviewed(
        status=MarketplaceReview.Status.REJECTED,
        reviewed_by=rejected_by,
        notes=notes,
        findings_json=findings or {},
    )
    listing.security_review_status = MarketplaceListing.ReviewStatus.REJECTED
    listing.status = MarketplaceListing.Status.DRAFT
    listing.save(
        update_fields=["security_review_status", "status", "updated_at"]
    )
    _log_partner_event(
        app=listing.app,
        action="marketplace.partner_reject",
        payload={"listing_id": listing.pk, "review_id": review.pk, "notes": notes[:500]},
        actor=rejected_by,
    )
    return review


@transaction.atomic
def request_changes(
    review: MarketplaceReview,
    *,
    reviewer=None,
    notes: str = "",
    findings: dict[str, Any] | None = None,
) -> MarketplaceReview:
    """Soft reject — publisher must address findings and re-submit."""
    if review.review_type != MarketplaceReview.ReviewType.SECURITY:
        raise PartnerSubmissionError(
            "Only SECURITY reviews can be marked changes_required via this service."
        )
    listing = review.listing
    review.mark_reviewed(
        status=MarketplaceReview.Status.CHANGES_REQUIRED,
        reviewed_by=reviewer,
        notes=notes,
        findings_json=findings or {},
    )
    listing.security_review_status = MarketplaceListing.ReviewStatus.CHANGES_REQUIRED
    listing.save(update_fields=["security_review_status", "updated_at"])
    _log_partner_event(
        app=listing.app,
        action="marketplace.partner_changes_required",
        payload={"listing_id": listing.pk, "review_id": review.pk, "notes": notes[:500]},
        actor=reviewer,
    )
    return review


__all__ = [
    "PartnerSubmissionError",
    "submit_for_review",
    "list_pending_for_governance",
    "approve_partner_submission",
    "reject_partner_submission",
    "request_changes",
]
