"""Operator console for INVITING a school to the platform (2026-06-06).

Staff-only surface on the manager host. Lets operators invite a whole school by
email (with optional name/country prefill); the recipient opens the accept link
and is routed into the standard onboarding/signup workflow. Distinct from staff
invites (which add people to an existing tenant).

  * GET  /super/invite-school/                  — send form + invite list
  * POST /super/invite-school/                  — action = send | resend | revoke

The accept link lives on the PUBLIC site (``/accept-invite/``), which does not
route on the manager host, so we build it from ``settings.RMC_PUBLIC_SITE_URL``.
"""
from __future__ import annotations

import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views import View

from apps.schoolops.email_delivery import send_transactional
from apps.schools.models import TenantInvite

logger = logging.getLogger(__name__)

_INVITE_WINDOW_DAYS = 7
_CONSOLE_ROW_LIMIT = 300


def _public_base_url() -> str:
    return (
        getattr(settings, "RMC_PUBLIC_SITE_URL", "") or "https://runmycampus.com"
    ).rstrip("/")


def send_tenant_invite_email(invite: TenantInvite) -> None:
    """Send the invitation email. Never raises (mirrors send_transactional)."""
    accept_url = f"{_public_base_url()}/accept-invite/?token={invite.token}"
    school_hint = f" ({invite.school_name})" if invite.school_name else ""
    subject = "You're invited to set up your school on RunMyCampus"
    body = (
        f"Hello,\n\n"
        f"You've been invited to bring your school{school_hint} onto RunMyCampus.\n\n"
        f"Click the link below to accept and start the guided setup "
        f"(invitation valid for {_INVITE_WINDOW_DAYS} days):\n\n"
        f"{accept_url}\n\n"
        f"If you weren't expecting this, you can ignore this email.\n"
    )
    try:
        send_transactional(
            subject=subject,
            body=body,
            to=invite.email,
            from_email=settings.DEFAULT_FROM_EMAIL or "noreply@runmycampus.com",
            priority="transactional",
            async_send=True,
        )
    except (OSError, ConnectionError, ValueError, TypeError) as exc:
        logger.warning(
            "tenant invite email sync raise err=%s invite=%s",
            type(exc).__name__,
            getattr(invite, "id", None),
        )


@method_decorator(staff_member_required, name="dispatch")
class InviteSchoolConsoleView(View):
    """Send school invitations + manage pending/accepted/revoked invites."""

    template_name = "schoolops/super/invite_school.html"

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        return render(request, self.template_name, self._context())

    def _context(self) -> dict:
        counts = {"pending": 0, "accepted": 0, "expired": 0, "revoked": 0, "total": 0}
        rows = []
        qs = (
            # tenant-isolation-allow: platform-operator-console-lists-all-tenant-invites
            TenantInvite.objects.select_related("school", "invited_by").order_by(
                "-created_at"
            )
        )
        for inv in qs[:_CONSOLE_ROW_LIMIT]:
            status = inv.status
            counts[status] = counts.get(status, 0) + 1
            counts["total"] += 1
            rows.append(
                {
                    "id": str(inv.pk),
                    "email": inv.email,
                    "school_name": inv.school_name,
                    "country_code": inv.country_code,
                    "status": status,
                    "created_at": inv.created_at,
                    "expires_at": inv.expires_at,
                    "accepted_at": inv.accepted_at,
                    "invited_by": getattr(inv.invited_by, "email", ""),
                    "bound_school": getattr(inv.school, "name", ""),
                }
            )
        return {"page_title": "Invite a school", "rows": rows, "counts": counts}

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        action = (request.POST.get("action") or "").strip().lower()
        back = redirect("super:invite_school")

        if action == "send":
            email = (request.POST.get("email") or "").strip().lower()
            if not email or "@" not in email or len(email) > 254:
                messages.error(request, "Enter a valid email address.")
                return back
            existing = (
                # tenant-isolation-allow: platform-dedupe-pending-invite-by-unique-email
                TenantInvite.objects.filter(
                    email__iexact=email,
                    accepted_at__isnull=True,
                    revoked_at__isnull=True,
                    expires_at__gt=timezone.now(),
                ).first()
            )
            if existing is not None:
                messages.info(request, f"A pending invite already exists for {email}.")
                return back
            invite = TenantInvite.objects.create(
                email=email,
                school_name=(request.POST.get("school_name") or "").strip()[:255],
                country_code=(request.POST.get("country_code") or "").strip().upper()[:2],
                note=(request.POST.get("note") or "").strip()[:500],
                invited_by=request.user if request.user.is_authenticated else None,
                expires_at=timezone.now() + timezone.timedelta(days=_INVITE_WINDOW_DAYS),
            )
            send_tenant_invite_email(invite)
            logger.info(
                "super.tenant_invite.send by=%s invite=%s",
                getattr(request.user, "id", None),
                invite.id,
            )
            messages.success(request, f"Invitation sent to {email}.")
            return back

        import uuid as _uuid

        invite_id = (request.POST.get("invite_id") or "").strip()
        invite = None
        if invite_id:
            try:
                invite_pk = _uuid.UUID(invite_id)
            except (ValueError, TypeError):
                invite_pk = None
            if invite_pk is not None:
                # tenant-isolation-allow: platform-operator-action-on-specific-invite-by-uuid
                invite = TenantInvite.objects.filter(pk=invite_pk).first()
        if invite is None:
            messages.error(request, "That invite no longer exists.")
            return back

        if action == "resend":
            if invite.accepted_at is not None:
                messages.info(request, "That invite was already accepted.")
                return back
            invite.expires_at = timezone.now() + timezone.timedelta(days=_INVITE_WINDOW_DAYS)
            invite.revoked_at = None
            invite.save(update_fields=["expires_at", "revoked_at"])
            send_tenant_invite_email(invite)
            messages.success(request, f"Invitation re-sent to {invite.email}.")
            return back

        if action == "revoke":
            if invite.accepted_at is not None:
                messages.info(request, "Accepted invites cannot be revoked.")
                return back
            invite.revoked_at = timezone.now()
            invite.save(update_fields=["revoked_at"])
            messages.success(request, f"Invitation to {invite.email} revoked.")
            return back

        messages.error(request, "Unknown action.")
        return back
