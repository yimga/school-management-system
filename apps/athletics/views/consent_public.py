"""Anonymous guardian-facing participation-consent pages (token-in-URL).

Mirrors ``apps.people.views_transfer_consent``: the raw token is looked up by sha256
(never persisted), invalid/expired/decided tokens all render the SAME uniform 200 page
(anti-enumeration), and the decision transition is owned by the service /
``ParticipationConsent`` model. Standalone (no tenant shell) because the caller is
anonymous. Security headers: never-cache / no-store / Referrer-Policy: no-referrer so the
live token never lands in a shared cache, bfcache, or Referer header.
"""

from __future__ import annotations

import logging

from django.shortcuts import render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from apps.athletics.models import ParticipationConsent, ParticipationConsentError

logger = logging.getLogger(__name__)


def _secure(response):
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Frame-Options"] = "DENY"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _load(request):
    raw_token = (
        request.POST.get("token")
        if request.method == "POST"
        else request.GET.get("token")
    ) or ""
    consent = ParticipationConsent.lookup_by_raw_token(raw_token)
    if consent is not None and not consent.matches(raw_token):
        consent = None
    return raw_token, consent


@never_cache
@require_http_methods(["GET"])
def participation_consent_public(request):
    raw_token, consent = _load(request)
    usable = consent is not None and not consent.is_decided and not consent.is_expired
    if consent is not None and usable:
        consent.mark_first_seen()
    return _secure(
        render(
            request,
            "athletics/consent/landing.html",
            {
                "usable": usable,
                "consent": consent if usable else None,
                "token": raw_token if usable else "",
            },
        )
    )


@never_cache
@require_http_methods(["POST"])
def participation_consent_decide(request):
    raw_token, consent = _load(request)
    choice = (request.POST.get("choice") or "").strip().lower()
    outcome = "invalid"
    if consent is not None and choice in ("consent", "decline"):
        from apps.athletics.services.consent import record_consent_decision

        try:
            record_consent_decision(
                raw_token=raw_token,
                consented=(choice == "consent"),
                request=request,
            )
            outcome = "consented" if choice == "consent" else "declined"
        except ParticipationConsentError:
            outcome = "invalid"
    return _secure(
        render(
            request,
            "athletics/consent/decided.html",
            {"outcome": outcome},
        )
    )
