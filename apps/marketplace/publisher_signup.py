"""Self-serve publisher signup service.

Move 1 of the developer-platform burndown. A prospective publisher submits
a `PublisherSignupRequest` from a public form, receives an email-verify token,
and after operator approval the row is promoted into a `PublisherOrganization`
linked to the requester's user account.
"""

from __future__ import annotations

import secrets
from typing import Any

from django.db import transaction
from django.utils import timezone
from django.utils.text import slugify

from apps.marketplace.models import PublisherOrganization, PublisherSignupRequest


def _new_token() -> str:
    return secrets.token_urlsafe(40)


def _unique_slug(base: str) -> str:
    base_slug = slugify(base)[:60] or "publisher"
    candidate = base_slug
    suffix = 2
    while PublisherOrganization.objects.filter(slug=candidate).exists():
        candidate = f"{base_slug}-{suffix}"[:80]
        suffix += 1
    return candidate


@transaction.atomic
def submit_publisher_signup(
    *,
    organization_name: str,
    contact_email: str,
    contact_name: str = "",
    legal_name: str = "",
    country_code: str = "",
    website_url: str = "",
    intent: str = "",
    submitted_by=None,
) -> PublisherSignupRequest:
    """Create a PublisherSignupRequest with an unsent email-verify token.

    The caller is responsible for sending the verification email
    (see `apps.marketplace.publisher_signup.send_verification_email`).
    """

    if not organization_name.strip():
        raise ValueError("organization_name is required")
    if not contact_email.strip():
        raise ValueError("contact_email is required")

    return PublisherSignupRequest.objects.create(
        organization_name=organization_name.strip()[:255],
        legal_name=legal_name.strip()[:255],
        country_code=(country_code or "").upper()[:2],
        website_url=(website_url or "")[:500],
        contact_email=contact_email.strip().lower()[:254],
        contact_name=contact_name.strip()[:120],
        intent=intent.strip(),
        email_verify_token=_new_token(),
        submitted_by=submitted_by if (submitted_by and submitted_by.is_authenticated) else None,
    )


def verify_email_token(token: str) -> PublisherSignupRequest | None:
    """Mark a signup as email-verified. Returns the request, or None if invalid."""

    try:
        req = PublisherSignupRequest.objects.get(email_verify_token=token)
    except PublisherSignupRequest.DoesNotExist:
        return None
    if req.status != PublisherSignupRequest.Status.EMAIL_PENDING:
        return req
    req.status = PublisherSignupRequest.Status.EMAIL_VERIFIED
    req.email_verified_at = timezone.now()
    req.save(update_fields=["status", "email_verified_at", "updated_at"])
    return req


@transaction.atomic
def approve_signup(
    request_id: int,
    *,
    reviewer,
    reviewer_notes: str = "",
) -> PublisherOrganization:
    """Approve a verified signup and create the linked PublisherOrganization."""

    req = (
        PublisherSignupRequest.objects.select_for_update()
        .select_related("publisher")
        .get(pk=request_id)
    )
    if req.status == PublisherSignupRequest.Status.APPROVED and req.publisher_id:
        return req.publisher
    if req.status != PublisherSignupRequest.Status.EMAIL_VERIFIED:
        raise ValueError(
            f"Cannot approve signup in status {req.status!r}; email must be verified first."
        )
    publisher = PublisherOrganization.objects.create(
        slug=_unique_slug(req.organization_name),
        name=req.organization_name,
        legal_name=req.legal_name,
        country_code=req.country_code,
        verified_contact_email=req.contact_email,
        website_url=req.website_url,
        support_email=req.contact_email,
        verification_status=PublisherOrganization.VerificationStatus.VERIFIED,
    )
    req.status = PublisherSignupRequest.Status.APPROVED
    req.publisher = publisher
    req.reviewer = reviewer if (reviewer and getattr(reviewer, "is_authenticated", False)) else None
    if reviewer_notes:
        req.reviewer_notes = reviewer_notes
    req.decided_at = timezone.now()
    req.save(
        update_fields=[
            "status",
            "publisher",
            "reviewer",
            "reviewer_notes",
            "decided_at",
            "updated_at",
        ]
    )
    return publisher


@transaction.atomic
def reject_signup(
    request_id: int,
    *,
    reviewer,
    reviewer_notes: str = "",
) -> PublisherSignupRequest:
    req = PublisherSignupRequest.objects.select_for_update().get(pk=request_id)
    if req.status in {
        PublisherSignupRequest.Status.APPROVED,
        PublisherSignupRequest.Status.REJECTED,
        PublisherSignupRequest.Status.WITHDRAWN,
    }:
        return req
    req.status = PublisherSignupRequest.Status.REJECTED
    req.reviewer = reviewer if (reviewer and getattr(reviewer, "is_authenticated", False)) else None
    if reviewer_notes:
        req.reviewer_notes = reviewer_notes
    req.decided_at = timezone.now()
    req.save(
        update_fields=["status", "reviewer", "reviewer_notes", "decided_at", "updated_at"]
    )
    return req


def send_verification_email(req: PublisherSignupRequest, *, base_url: str) -> bool:
    """Send the email-verify link. Returns True on success.

    The body uses a plain-text template so it works regardless of HTML rendering.
    """

    from django.core.mail import send_mail

    verify_url = (
        base_url.rstrip("/")
        + f"/marketplace/publisher/verify-email/?token={req.email_verify_token}"
    )
    body = (
        f"Hi {req.contact_name or 'there'},\n\n"
        f"Thanks for applying to publish on the RunMyCampus marketplace as "
        f"{req.organization_name}.\n\n"
        "Confirm the email address on this signup by visiting:\n"
        f"  {verify_url}\n\n"
        "After confirmation, an RMC operator will review your application and "
        "respond within a few business days.\n\n"
        "If you didn't submit this, you can safely ignore this email.\n"
    )
    try:
        send_mail(
            subject="Verify your RunMyCampus publisher application",
            message=body,
            from_email=None,
            recipient_list=[req.contact_email],
            fail_silently=False,
        )
        return True
    except Exception:
        return False


def link_user_to_publisher(user, publisher: PublisherOrganization) -> bool:
    """Set publisher.verified_contact_email to the user's email if currently blank.

    Used after first login of an approved-but-not-yet-linked publisher.
    """

    if not user or not getattr(user, "email", None):
        return False
    if publisher.verified_contact_email:
        return publisher.verified_contact_email.lower() == user.email.lower()
    publisher.verified_contact_email = user.email
    publisher.save(update_fields=["verified_contact_email", "updated_at"])
    return True
