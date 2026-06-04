"""Consent preference centre (audit residual closeout).

A logged-in surface where a user manages email communication consent for their
OWN account. Toggling writes a :class:`apps.communication.models_consent.ConsentEvent`
AND mirrors to the email suppression list, so the choice is honoured by both
the transactional engine's pre-send gate and the compliance audit trail.

Why email-only
--------------
We only let a user act on identifiers we KNOW belong to them — their account
email. SMS / WhatsApp opt-out is possession-proven: it must come from the
``STOP`` keyword texted from the phone itself (handled by
:mod:`apps.communication.views_sms_inbound_webhook`), never from a logged-in
form, because that would let anyone opt an arbitrary number out. The page
surfaces the SMS/WhatsApp channels read-only with that guidance.
"""
from __future__ import annotations

import logging

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET", "POST"])
def consent_preferences(request):
    """View + toggle the logged-in user's email communication consent."""
    email = (getattr(request.user, "email", "") or "").strip()
    school = getattr(request, "school", None)

    from apps.communication.consent import (
        hash_identifier,
        is_channel_suppressed,
        record_consent_event,
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip()
        if not email:
            messages.error(request, "Your account has no email address on file.")
            return redirect(reverse("communication:consent_preferences"))
        if action == "opt_out":
            record_consent_event(
                channel="email", identifier=email, action="withdrawn",
                reason="preference_centre", source="preference_centre", school=school,
            )
            try:
                from apps.schoolops.email_delivery import suppress_recipient

                suppress_recipient(
                    email, reason="unsubscribe", source="preference_centre",
                )
            except Exception:  # noqa: BLE001 — mirror is best-effort
                logger.warning("consent_preferences suppression mirror failed")
            messages.success(request, "You have been unsubscribed from marketing email.")
        elif action == "opt_in":
            record_consent_event(
                channel="email", identifier=email, action="granted",
                reason="preference_centre", source="preference_centre", school=school,
            )
            try:
                from apps.schoolops.email_delivery import lift_suppression

                lift_suppression(email)
            except Exception:  # noqa: BLE001 — mirror is best-effort
                logger.warning("consent_preferences suppression lift failed")
            messages.success(request, "You are subscribed to email again.")
        return redirect(reverse("communication:consent_preferences"))

    email_opted_out = bool(email) and is_channel_suppressed("email", email)
    history = []
    if email:
        try:
            from apps.communication.models_consent import ConsentEvent

            id_hash = hash_identifier(email)
            # tenant-isolation-allow: consent history scoped to the requester's own hashed email
            history = list(
                ConsentEvent.objects.filter(
                    channel="email", identifier_hash=id_hash,
                ).order_by("-created_at")[:10]
            )
        except Exception:  # noqa: BLE001 — history is best-effort
            history = []

    context = {
        "page_title": "Communication preferences",
        "account_email": email,
        "email_opted_out": email_opted_out,
        "history": history,
    }
    return render(request, "communication/preferences/consent_centre.html", context)


__all__ = ["consent_preferences"]
