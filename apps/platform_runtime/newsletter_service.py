"""Newsletter subscription service (v4.00.98 Phase 3).

Public-facing surface for the marketing list. Three operations:

* :func:`request_subscription`  — public form posts here; creates / refreshes
  the row in ``pending`` state and emails a double-opt-in verification token.
* :func:`confirm_subscription`  — verification link lands here; flips status
  to ``confirmed`` and emails the welcome row.
* :func:`unsubscribe`           — one-click unsubscribe; flips status to
  ``unsubscribed`` and stops all future sends in the ``marketing`` class.

Tokens are TimestampSigner-signed (RFC-style); 7-day TTL for confirmation,
no TTL for unsubscribe (operators may revoke a stolen token by re-issuing).
NEVER stores or logs the raw IP — only sha256[:16].
"""

from __future__ import annotations

import hashlib
import logging

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.urls import reverse
from django.utils import timezone

logger = logging.getLogger(__name__)


_CONFIRM_SALT = "rmc.newsletter.confirm.v4.00.98"
_UNSUBSCRIBE_SALT = "rmc.newsletter.unsubscribe.v4.00.98"
# 7 days for confirmation links
_CONFIRM_MAX_AGE_SECONDS = 60 * 60 * 24 * 7


def _hash_ip(ip: str) -> str:
    if not ip:
        return ""
    return hashlib.sha256(ip.strip().encode("utf-8")).hexdigest()[:16]


def _signer(salt: str) -> TimestampSigner:
    return TimestampSigner(salt=salt)


def _build_confirm_url(email: str) -> str:
    token = _signer(_CONFIRM_SALT).sign(email.strip().lower())
    try:
        path = reverse("platform_runtime:newsletter_confirm", kwargs={"token": token})
    except Exception:
        path = f"/platform-runtime/newsletter/confirm/{token}/"
    site_url = (getattr(settings, "RMC_PUBLIC_SITE_URL", "") or "").rstrip("/")
    return f"{site_url}{path}" if site_url else path


def _build_unsubscribe_url(email: str) -> str:
    token = _signer(_UNSUBSCRIBE_SALT).sign(email.strip().lower())
    try:
        path = reverse("platform_runtime:newsletter_unsubscribe", kwargs={"token": token})
    except Exception:
        path = f"/platform-runtime/newsletter/unsubscribe/{token}/"
    site_url = (getattr(settings, "RMC_PUBLIC_SITE_URL", "") or "").rstrip("/")
    return f"{site_url}{path}" if site_url else path


def request_subscription(
    *,
    email: str,
    source: str = "",
    ip: str = "",
    utm_source: str = "",
    utm_medium: str = "",
    utm_campaign: str = "",
) -> dict:
    """Public form POST handler. Idempotent — re-submitting refreshes the
    confirmation token and re-sends the verification email."""

    from apps.platform_runtime.models import (
        NewsletterSubscription,
        NewsletterSubscriptionStatus,
    )

    addr = (email or "").strip().lower()
    if not addr or "@" not in addr or len(addr) > 254:
        return {"ok": False, "reason": "invalid_email"}

    # tenant-isolation-allow: public-marketing-newsletter-no-tenant-scope
    row, created = NewsletterSubscription.objects.get_or_create(email=addr)
    if row.status == NewsletterSubscriptionStatus.UNSUBSCRIBED:
        # Re-subscription path: send confirmation again, do NOT auto-flip.
        row.status = NewsletterSubscriptionStatus.PENDING
        row.unsubscribed_at = None

    if source and not row.source:
        row.source = source[:64]
    if ip:
        row.ip_hash = _hash_ip(ip)
    if utm_source:
        row.utm_source = utm_source[:64]
    if utm_medium:
        row.utm_medium = utm_medium[:64]
    if utm_campaign:
        row.utm_campaign = utm_campaign[:128]

    row.confirmation_token = _signer(_CONFIRM_SALT).sign(addr)
    row.unsubscribe_token = _signer(_UNSUBSCRIBE_SALT).sign(addr)
    row.save()

    # Fire the matrix verification email.
    try:
        from apps.platform_runtime.platform_email_matrix import (
            dispatch_email_for_event,
        )

        dispatch_email_for_event(
            "newsletter.subscription.verify",
            {
                "to": addr,
                "verification_url": _build_confirm_url(addr),
                "unsubscribe_url": _build_unsubscribe_url(addr),
            },
            idempotency_key=f"newsletter_verify:{row.pk}:{int(row.created_at.timestamp() if row.created_at else 0)}",
        )
    except Exception:
        logger.exception("newsletter_verification_dispatch_failed")

    return {
        "ok": True,
        "created": bool(created),
        "status": row.status,
        "verification_sent": True,
    }


def confirm_subscription(token: str) -> dict:
    """Land the verification link. Marks the row as ``confirmed`` and fires
    the welcome email. Idempotent — replaying a valid token is fine."""

    from apps.platform_runtime.models import (
        NewsletterSubscription,
        NewsletterSubscriptionStatus,
    )

    if not token:
        return {"ok": False, "reason": "missing_token"}

    try:
        email = _signer(_CONFIRM_SALT).unsign(token, max_age=_CONFIRM_MAX_AGE_SECONDS)
    except SignatureExpired:
        return {"ok": False, "reason": "expired_token"}
    except BadSignature:
        return {"ok": False, "reason": "bad_token"}

    # tenant-isolation-allow: public-marketing-newsletter-no-tenant-scope
    row = NewsletterSubscription.objects.filter(email__iexact=email).first()
    if row is None:
        return {"ok": False, "reason": "no_subscription"}

    if row.status == NewsletterSubscriptionStatus.CONFIRMED:
        return {"ok": True, "already_confirmed": True, "email": row.email}

    row.status = NewsletterSubscriptionStatus.CONFIRMED
    row.confirmed_at = timezone.now()
    row.confirmation_token = ""  # one-time
    row.save()

    try:
        from apps.platform_runtime.platform_email_matrix import (
            dispatch_email_for_event,
        )

        dispatch_email_for_event(
            "newsletter.subscription.confirmed",
            {
                "to": row.email,
                "unsubscribe_url": _build_unsubscribe_url(row.email),
            },
            idempotency_key=f"newsletter_welcome:{row.pk}",
        )
    except Exception:
        logger.exception("newsletter_welcome_dispatch_failed")

    return {"ok": True, "confirmed": True, "email": row.email}


def unsubscribe(token: str) -> dict:
    """One-click unsubscribe. Idempotent — replaying a token on an
    already-unsubscribed row is fine."""

    from apps.platform_runtime.models import (
        NewsletterSubscription,
        NewsletterSubscriptionStatus,
    )

    if not token:
        return {"ok": False, "reason": "missing_token"}

    try:
        email = _signer(_UNSUBSCRIBE_SALT).unsign(token)
    except BadSignature:
        return {"ok": False, "reason": "bad_token"}

    # tenant-isolation-allow: public-marketing-newsletter-no-tenant-scope
    row = NewsletterSubscription.objects.filter(email__iexact=email).first()
    if row is None:
        return {"ok": False, "reason": "no_subscription"}

    if row.status == NewsletterSubscriptionStatus.UNSUBSCRIBED:
        return {"ok": True, "already_unsubscribed": True, "email": row.email}

    row.status = NewsletterSubscriptionStatus.UNSUBSCRIBED
    row.unsubscribed_at = timezone.now()
    row.save()

    return {"ok": True, "unsubscribed": True, "email": row.email}
