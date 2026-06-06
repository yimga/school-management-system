"""Operator console for signup email-verification management (2026-06-06).

Staff-only surface on the manager host that lets operators see every pending /
expired / stale signup verification and act on it directly:

  * GET  /super/signup-verifications/                      — console list
  * POST /super/signup-verifications/<uuid:pk>/action/     — resend | regenerate

``resend``     re-sends the current verification link (extending the 2-day
              window if it had already expired, so the resent link works).
``regenerate`` rotates the token (old links die) AND refreshes the window,
              then sends — the right tool when a link may have leaked.

The verify link lives on the PUBLIC site (``/verify-signup/``), which does not
route on the manager host, so we pass ``settings.RMC_PUBLIC_SITE_URL`` to the
shared sender. Operators are trusted, so the public per-email/IP resend throttle
is intentionally bypassed here (every action is logged + audited instead).
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

from apps.schools.models import SignupVerification
from apps.schools.signup_views import _send_signup_verification_email

logger = logging.getLogger(__name__)

# A pending verification older than this is "stale" (the operator should chase
# it). Mirrors the signup_verification_stale_sweep Celery alert threshold.
_STALE_AFTER_HOURS = 24
_CONSOLE_ROW_LIMIT = 300
_VERIFY_WINDOW_DAYS = 2


def _public_base_url() -> str:
    """Public site origin for the verify link (manager host can't route it)."""
    return (getattr(settings, "RMC_PUBLIC_SITE_URL", "") or "https://runmycampus.com").rstrip("/")


def _status_of(v, now) -> str:
    if v.verified_at is not None:
        return "verified"
    if v.expires_at and v.expires_at < now:
        return "expired"
    return "pending"


@method_decorator(staff_member_required, name="dispatch")
class SignupVerificationConsoleView(View):
    """List signup verifications with status + per-row resend/regenerate."""

    template_name = "schoolops/super/signup_verifications.html"

    def get(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        now = timezone.now()
        status_filter = (request.GET.get("status") or "").strip().lower()
        stale_cutoff = now - timezone.timedelta(hours=_STALE_AFTER_HOURS)

        qs = (
            # tenant-isolation-allow: platform-operator-console-lists-all-pending-tenant-signups
            SignupVerification.objects.select_related("school").order_by("-created_at")
        )
        rows = []
        counts = {"pending": 0, "expired": 0, "verified": 0, "stale": 0, "total": 0}
        for v in qs[:_CONSOLE_ROW_LIMIT]:
            status = _status_of(v, now)
            counts[status] = counts.get(status, 0) + 1
            counts["total"] += 1
            is_stale = (
                status == "pending"
                and v.created_at is not None
                and v.created_at < stale_cutoff
            )
            if is_stale:
                counts["stale"] += 1
            if status_filter in ("pending", "expired", "verified") and status != status_filter:
                continue
            if status_filter == "stale" and not is_stale:
                continue
            rows.append(
                {
                    "id": str(v.pk),
                    "email": v.email,
                    "school_name": getattr(v.school, "name", ""),
                    "school_slug": getattr(v.school, "slug", ""),
                    "school_active": bool(getattr(v.school, "is_active", False)),
                    "status": status,
                    "is_stale": is_stale,
                    "created_at": v.created_at,
                    "expires_at": v.expires_at,
                    "verified_at": v.verified_at,
                }
            )

        context = {
            "page_title": "Signup verifications",
            "rows": rows,
            "counts": counts,
            "status_filter": status_filter,
            "stale_after_hours": _STALE_AFTER_HOURS,
            "row_limit": _CONSOLE_ROW_LIMIT,
        }
        return render(request, self.template_name, context)


@method_decorator(staff_member_required, name="dispatch")
class SignupVerificationActionView(View):
    """Resend or regenerate a single signup verification (operator-trusted)."""

    def post(self, request: HttpRequest, pk, *args, **kwargs) -> HttpResponse:
        action = (request.POST.get("action") or "").strip().lower()
        back = redirect("super:signup_verifications")

        verification = (
            # tenant-isolation-allow: platform-operator-action-on-specific-signup-by-uuid-pk
            SignupVerification.objects.select_related("school")
            .filter(pk=pk)
            .first()
        )
        if verification is None:
            messages.error(request, "That signup verification no longer exists.")
            return back

        if verification.verified_at is not None:
            messages.info(
                request,
                f"{verification.email} is already verified — nothing to resend.",
            )
            return back

        if action not in ("resend", "regenerate"):
            messages.error(request, "Unknown action.")
            return back

        now = timezone.now()
        update_fields = []
        if action == "regenerate":
            import uuid as _uuid

            verification.token = _uuid.uuid4()
            update_fields.append("token")
        # Both actions ensure the link the operator sends is actually valid.
        if action == "regenerate" or (verification.expires_at and verification.expires_at < now):
            verification.expires_at = now + timezone.timedelta(days=_VERIFY_WINDOW_DAYS)
            update_fields.append("expires_at")
        if update_fields:
            verification.save(update_fields=update_fields)

        _send_signup_verification_email(
            request, verification, base_url=_public_base_url()
        )
        logger.info(
            "super.signup_verification.%s by=%s school_id=%s",
            action,
            getattr(request.user, "id", None),
            getattr(verification.school, "id", None),
        )
        verb = "regenerated and re-sent" if action == "regenerate" else "re-sent"
        messages.success(
            request,
            f"Verification link {verb} to {verification.email}.",
        )
        return back
