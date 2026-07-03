"""Anonymous guardian-facing transfer consent pages (Wave B).

Token-in-URL, anti-enumeration: invalid/expired/decided tokens all render
the SAME uniform 200 page shape (mirrors the Migration Cloud guardian
consent surface). The raw token never persists server-side — lookup is by
sha256 and the decision transitions are owned by the TransferConsent model.
"""

from __future__ import annotations

import logging

from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.people.models_transfer_consent import (
    TransferConsent,
    TransferConsentError,
)

logger = logging.getLogger(__name__)


def _load(request):
    raw_token = (
        request.POST.get("token")
        if request.method == "POST"
        else request.GET.get("token")
    ) or ""
    consent = TransferConsent.lookup_by_raw_token(raw_token)
    if consent is not None and not consent.matches(raw_token):
        consent = None
    return raw_token, consent


@require_http_methods(["GET"])
def transfer_consent_landing(request):
    raw_token, consent = _load(request)
    usable = consent is not None and not consent.is_decided and not consent.is_expired
    if consent is not None and usable:
        consent.mark_first_seen()
    return render(
        request,
        "people/transfer_consent/landing.html",
        {
            "usable": usable,
            "consent": consent if usable else None,
            "token": raw_token if usable else "",
        },
    )


@require_http_methods(["POST"])
def transfer_consent_decide(request):
    _raw_token, consent = _load(request)
    choice = (request.POST.get("choice") or "").strip().lower()
    outcome = "invalid"
    if consent is not None and choice in ("consent", "decline"):
        try:
            if choice == "consent":
                consent.consent(request)
                outcome = "consented"
            else:
                consent.decline(request)
                outcome = "declined"
        except TransferConsentError:
            outcome = "invalid"
    return render(
        request,
        "people/transfer_consent/decided.html",
        {"outcome": outcome},
    )
