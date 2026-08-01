"""Passwordless sign-in — single-use, short-lived magic links.

A 2026 best practice for low-friction access (parents/teachers who sign in
sporadically). The link works once, expires quickly, and requests are rate-limited
+ enumeration-safe (callers always show a generic message). MFA, if enrolled, is
still enforced by RequireMFAMiddleware after the passwordless login.
"""

from __future__ import annotations

import logging

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

logger = logging.getLogger(__name__)

MAGIC_LINK_TTL_MINUTES = 15
_MAX_PER_WINDOW = 5
_RATE_WINDOW_MINUTES = 15


def _client_ip(request):
    if request is None:
        return None
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip() or None
    return request.META.get("REMOTE_ADDR") or None


def request_magic_link(email, *, school=None, request=None) -> bool:
    """Create + email a magic link for the active account with ``email`` (if any).
    Returns True when a link was emailed. Callers MUST show a generic message
    regardless of the result — never reveal whether the account exists."""
    from django.contrib.auth import get_user_model

    from apps.accounts.models import LoginMagicLink

    User = get_user_model()
    email = (email or "").strip().lower()
    if not email or "@" not in email:
        return False
    user = (
        User.objects.filter(
            Q(email__iexact=email) | Q(username__iexact=email), is_active=True
        )
        .order_by("id")
        .first()
    )
    if user is None:
        return False

    now = timezone.now()
    window_start = now - timezone.timedelta(minutes=_RATE_WINDOW_MINUTES)
    # tenant-isolation-allow: magic-link-rate-limit-count-is-scoped-by-resolved-user-not-tenant
    if LoginMagicLink.objects.filter(user=user, created_at__gte=window_start).count() >= _MAX_PER_WINDOW:
        return False  # rate-limited; requester still sees the generic message

    link = LoginMagicLink.objects.create(
        user=user,
        school=school,
        expires_at=now + timezone.timedelta(minutes=MAGIC_LINK_TTL_MINUTES),
        requested_ip=_client_ip(request),
    )
    return _send_magic_link_email(link, request=request)


def _magic_link_url(link, *, request=None) -> str:
    from django.urls import reverse

    path = reverse("accounts:magic_link_login", kwargs={"token": str(link.token)})
    return request.build_absolute_uri(path) if request is not None else path


def _send_magic_link_email(link, *, request=None) -> bool:
    from django.utils.translation import gettext as _

    url = _magic_link_url(link, request=request)
    try:
        from apps.schoolops.email_delivery import send_transactional

        result = send_transactional(
            subject=_("Your sign-in link"),
            body=_(
                "Use this link to sign in. It works once and expires in "
                "%(mins)d minutes.\n\n%(url)s\n\n"
                "If you did not request this, you can safely ignore this email."
            )
            % {"mins": MAGIC_LINK_TTL_MINUTES, "url": url},
            to=[link.user.email],
            priority="transactional",
            school=link.school,
            idempotency_key=f"magic_link:{link.token}",
        )
    except Exception:  # noqa: BLE001 - email failure must not break the request
        logger.warning("accounts.magic_link_email_failed")
        return False
    return bool(result.get("ok") or result.get("queued"))


def consume_magic_link(token, *, school=None):
    """Return the user for a valid, unused, unexpired token (marking it used), else
    None. Scoped to ``school`` when the link carried one."""
    from apps.accounts.models import LoginMagicLink

    with transaction.atomic():
        link = (
            LoginMagicLink.objects.select_for_update()
            .filter(token=str(token))
            .select_related("user")
            .first()
        )
        if link is None or not link.is_valid:
            return None
        if school is not None and link.school_id and link.school_id != school.id:
            return None
        # tenant-isolation-allow: magic-link-marked-used-by-primary-key-on-already-validated-single-row
        LoginMagicLink.objects.filter(pk=link.pk, used_at__isnull=True).update(
            used_at=timezone.now()
        )
        return link.user
