"""Tell a school's admins that a box is waiting to be adopted.

This is the half of the pairing design that makes DEFERRED approval work rather than
merely be permitted. The technician is at the box; the person holding cloud admin is
usually not, and often not that day. Without a nudge, "the request waits 72 hours"
just means nobody notices for 72 hours.

It rides ``apps.communication.notification_service.send_email``, which is the same
rail the offboarding notices use, so on an edge deployment with
``RMC_EMAIL_OFFLINE_QUEUE`` the message is PARKED durably and forwarded when the link
returns instead of being dropped by a console backend that reports a false success.

Note what is deliberately NOT here: a link that approves. The message carries the code
and where to go; approving still requires signing in to the tenant. A one-click
approve link in an email would move the authorization decision back out of the
authenticated session, which is the exact property the whole box->cloud direction
exists to preserve.
"""
from __future__ import annotations

import logging
import os

from django.conf import settings

logger = logging.getLogger(__name__)


def notifications_enabled() -> bool:
    return os.environ.get(
        "RMC_EDGE_PAIRING_NOTIFY_ENABLED", "1"
    ).strip().lower() in ("1", "true", "yes", "on")


def _sync_center_url(school) -> str:
    """Where the approver goes. Tenant host, because that is where they sign in."""
    base = (
        os.environ.get("RMC_TENANT_BASE_URL", "").strip()
        or getattr(settings, "RMC_EDGE_OPERATOR_BASE", "")
        or ""
    ).rstrip("/")
    if not base:
        domain = (
            getattr(settings, "MULTI_TENANT_BASE_DOMAIN", "") or "runmycampus.com"
        ).strip()
        slug = getattr(school, "slug", "") or ""
        base = f"https://{slug}.{domain}" if slug else ""
    return f"{base}/siteconfig/sync-center/#pairing" if base else "the Sync Center"


def send_pairing_request_alert(request) -> None:
    """Email the school's admins about one pending pairing request.

    Never raises — the caller treats notification as best-effort, because the request
    is already durable and the Sync Center is the authoritative surface.
    """
    if not notifications_enabled():
        return
    school = getattr(request, "school", None)
    if school is None:
        return
    try:
        from apps.communication.notification_service import send_email
        from apps.schools.tenant_offboarding_notifications import school_admin_emails
    except ImportError:
        logger.warning(
            "sync_engine.pairing notify skipped: notification rails unavailable"
        )
        return

    recipients = school_admin_emails(school)
    if not recipients:
        logger.info(
            "sync_engine.pairing: no admin email on %s; request %s waits in the "
            "Sync Center only",
            getattr(school, "slug", "?"),
            request.user_code,
        )
        return

    where = _describe_box(request)
    body = (
        f"A RunMyCampus box is asking to pair with {school.name}.\n\n"
        f"    Pairing code:  {request.user_code}\n"
        f"    Box:           {where}\n"
        f"    Requested:     {request.created_at:%Y-%m-%d %H:%M} UTC\n"
        f"    Expires:       {request.expires_at:%Y-%m-%d %H:%M} UTC\n\n"
        "If you recognise this box, sign in and approve it:\n"
        f"    {_sync_center_url(school)}\n\n"
        "Approving lets that box sync this school's data with the cloud. If you do "
        "not recognise it, deny the request — the code alone gives it no access, and "
        "it expires on its own if nobody acts.\n"
    )
    send_email(
        recipients,
        f"Approve a box for {school.name}? Code {request.user_code}",
        body,
        school=school,
        fail_silently=True,
    )
    logger.info(
        "sync_engine.pairing: alerted %d admin(s) about %s",
        len(recipients),
        request.user_code,
    )


def _describe_box(request) -> str:
    """One line an admin can recognise a machine by."""
    bits = [
        b
        for b in (
            (request.box_label or "").strip(),
            (request.box_hostname or "").strip(),
            str(request.box_ip) if request.box_ip else "",
        )
        if b
    ]
    return " · ".join(bits) if bits else "an unlabelled box"


__all__ = ["notifications_enabled", "send_pairing_request_alert"]
