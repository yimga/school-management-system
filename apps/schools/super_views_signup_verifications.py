"""Operator console for signup email-verification management (2026-06-06).

Staff-only surface on the manager host — a verification & onboarding command
centre that lets operators see every pending / expired / stale signup
verification, understand WHY a tenant hasn't verified (email bounced? in spam?),
and act on it directly:

  * GET  /super/signup-verifications/                      — console list
  * POST /super/signup-verifications/                      — bulk: resend_stale
  * POST /super/signup-verifications/<uuid:pk>/action/     — resend | regenerate

``resend``     re-sends the current verification link (extending the 2-day
              window if it had already expired, so the resent link works).
``regenerate`` rotates the token (old links die) AND refreshes the window,
              then sends — the right tool when a link may have leaked.
``resend_stale`` (bulk) re-sends every pending verification older than the
              stale threshold, refreshing any that have lapsed.

100X (2026-06-08): per-row email-deliverability health (cross-referenced from
``EmailDeliveryEvent`` by recipient hash — surfaces bounces so operators see
why a link never arrived), a signup funnel band with conversion %, a one-click
copy-the-verify-link action (resend through any channel, bypassing spam), and a
bulk "resend all stale" action.

The verify link lives on the PUBLIC site (``/verify-signup/``), which does not
route on the manager host, so we pass ``settings.RMC_PUBLIC_SITE_URL`` to the
shared sender. Operators are trusted, so the public per-email/IP resend throttle
is intentionally bypassed here (every action is logged + audited instead).
"""
from __future__ import annotations

import hashlib
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views import View

from apps.schools.models import SignupVerification
from apps.schools.signup_views import _send_signup_verification_email

logger = logging.getLogger(__name__)

# A pending verification older than this is "stale" (the operator should chase
# it). Mirrors the signup_verification_stale_sweep Celery alert threshold.
_STALE_AFTER_HOURS = 24
_CONSOLE_ROW_LIMIT = 300
_VERIFY_WINDOW_DAYS = 2
_BULK_RESEND_CAP = 100  # magic-number-allow: bulk resend-stale safety cap
_DELIVERY_LOOKBACK_DAYS = 30
_DELIVERY_EVENT_SCAN_CAP = 1000  # magic-number-allow: delivery-event batch scan cap
_TO_HASH_LEN = 12  # mirrors apps.schoolops.email_delivery._TO_HASH_LEN


def _public_base_url() -> str:
    """Public site origin for the verify link (manager host can't route it)."""
    return (getattr(settings, "RMC_PUBLIC_SITE_URL", "") or "https://runmycampus.com").rstrip("/")


def _verify_url(token) -> str:
    """The clickable verification link an operator can copy + send anywhere."""
    return f"{_public_base_url()}/verify-signup/?token={token}"


def _audit_resend(school, action: str, actor_id) -> None:
    """Best-effort durable audit row for a verification-email (re)send action."""
    try:
        from apps.schools.models import SchoolProvisioningEvent

        SchoolProvisioningEvent.log_event(
            school=school,
            event_type=SchoolProvisioningEvent.EventType.INFO,
            status="INFO",
            message=f"Signup verification {action} by operator {actor_id}",
            payload={"action": action, "actor_id": str(actor_id or "")},
        )
    except (ImportError, AttributeError, TypeError, ValueError, OSError):
        pass


def _status_of(v, now) -> str:
    if v.verified_at is not None:
        return "verified"
    if v.expires_at and v.expires_at < now:
        return "expired"
    return "pending"


def _to_hash(email: str) -> str:
    """sha256(email.lower())[:12] — mirrors email_delivery._hash_recipient so we
    can correlate a recipient with their EmailDeliveryEvent rows."""
    norm = (email or "").strip().lower().encode("utf-8")
    return hashlib.sha256(norm).hexdigest()[:_TO_HASH_LEN]


def _email_health_for(emails) -> dict:
    """Map ``email -> {state, when, detail}`` from the most recent delivery event.

    ``state`` ∈ {delivered, bounced, failed}. Reflects the latest email of any
    kind sent to that address (a recent bounce is a strong signal the
    verification link never arrived). Degrades to ``{}`` on any error.
    """
    health: dict = {}
    try:
        from apps.schoolops.models_email_delivery import EmailDeliveryEvent
    except Exception:  # noqa: BLE001 - optional cross-reference, never fatal
        return health
    hash_to_email: dict = {}
    for e in emails:
        if e:
            hash_to_email.setdefault(_to_hash(e), e)
    if not hash_to_email:
        return health
    cutoff = timezone.now() - timezone.timedelta(days=_DELIVERY_LOOKBACK_DAYS)
    try:
        events = list(
            # tenant-isolation-allow: platform email-delivery log keyed by recipient hash, not tenant-scoped
            EmailDeliveryEvent.objects.filter(
                to_hash__in=list(hash_to_email.keys()), created_at__gte=cutoff
            )
            .order_by("-created_at")
            .values("to_hash", "ok", "bounced", "bounce_kind", "created_at")[
                :_DELIVERY_EVENT_SCAN_CAP
            ]
        )
    except Exception:  # noqa: BLE001 - delivery log is best-effort context
        return health
    seen: set = set()
    for ev in events:
        h = ev["to_hash"]
        if h in seen:
            continue
        seen.add(h)
        email = hash_to_email.get(h)
        if not email:
            continue
        if ev["bounced"]:
            state = "bounced"
        elif ev["ok"]:
            state = "delivered"
        else:
            state = "failed"
        health[email] = {
            "state": state,
            "when": ev["created_at"],
            "detail": ev.get("bounce_kind") or "",
        }
    return health


@method_decorator(staff_member_required, name="dispatch")
class SignupVerificationConsoleView(View):
    """List signup verifications with status, deliverability + resend/regenerate."""

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
                    "verify_url": _verify_url(v.token),
                }
            )

        # Email-deliverability health for the rows on screen (batch one query).
        health = _email_health_for([r["email"] for r in rows])
        bounced_count = 0
        for r in rows:
            r["health"] = health.get(r["email"])
            if r["health"] and r["health"]["state"] == "bounced" and r["status"] != "verified":
                bounced_count += 1

        total = counts["total"] or 0
        conversion_pct = round((counts["verified"] / total) * 100) if total else 0

        context = {
            "page_title": "Signup verifications",
            "rows": rows,
            "counts": counts,
            "conversion_pct": conversion_pct,
            "bounced_count": bounced_count,
            "status_filter": status_filter,
            "stale_after_hours": _STALE_AFTER_HOURS,
            "row_limit": _CONSOLE_ROW_LIMIT,
        }
        return render(request, self.template_name, context)

    def post(self, request: HttpRequest, *args, **kwargs) -> HttpResponse:
        """Bulk actions on the list surface (currently: resend every stale link)."""
        action = (request.POST.get("action") or "").strip().lower()
        back = redirect("super:signup_verifications")
        if action != "resend_stale":
            messages.error(request, _("Unknown bulk action."))
            return back

        now = timezone.now()
        stale_cutoff = now - timezone.timedelta(hours=_STALE_AFTER_HOURS)
        stale = (
            # tenant-isolation-allow: platform-operator-bulk-resend-of-all-stale-tenant-signups
            SignupVerification.objects.select_related("school")
            .filter(verified_at__isnull=True, created_at__lt=stale_cutoff)
            .order_by("created_at")[:_BULK_RESEND_CAP]
        )
        sent = 0
        for v in stale:
            if v.expires_at and v.expires_at < now:
                v.expires_at = now + timezone.timedelta(days=_VERIFY_WINDOW_DAYS)
                v.save(update_fields=["expires_at"])
            _send_signup_verification_email(request, v, base_url=_public_base_url())
            _audit_resend(v.school, "resend_stale", getattr(request.user, "id", None))
            sent += 1
        logger.info(
            "super.signup_verification.resend_stale by=%s count=%s",
            getattr(request.user, "id", None),
            sent,
        )
        if sent:
            messages.success(
                request,
                _("Re-sent %(n)s stale verification link(s).") % {"n": sent},
            )
        else:
            messages.info(request, _("No stale verifications to resend."))
        return back


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
            messages.error(request, _("That signup verification no longer exists."))
            return back

        if verification.verified_at is not None:
            messages.info(
                request,
                _("%(email)s is already verified — nothing to resend.")
                % {"email": verification.email},
            )
            return back

        if action not in ("resend", "regenerate"):
            messages.error(request, _("Unknown action."))
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
        _audit_resend(verification.school, action, getattr(request.user, "id", None))
        logger.info(
            "super.signup_verification.%s by=%s school_id=%s",
            action,
            getattr(request.user, "id", None),
            getattr(verification.school, "id", None),
        )
        verb = _("regenerated and re-sent") if action == "regenerate" else _("re-sent")
        messages.success(
            request,
            _("Verification link %(verb)s to %(email)s.")
            % {"verb": verb, "email": verification.email},
        )
        return back
