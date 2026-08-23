"""Guardian participation-consent orchestration.

Thin service wrappers around the ``ParticipationConsent`` model's own
mint / consent / decline discipline. The raw token is surfaced exactly once
(from ``mint``) and never logged; guardian emails are never logged.
"""

from __future__ import annotations

import logging

from django.db import transaction

from apps.athletics.constants import CONSENT_TEXT_VERSION
from apps.athletics.models import ParticipationConsent, ParticipationConsentError

logger = logging.getLogger(__name__)


def _consent_link(*, consent, raw_token: str, request) -> str:
    """Absolute, TENANT-host URL for the guardian consent page.

    The page has to be on the school's own host: athletics is mounted in
    config/tenant_urls.py and UrlConfSwitcherMiddleware serves a customer
    subdomain that urlconf, so a link built against any other host 404s for the
    guardian. Returns an empty string when there is no host context, and the
    caller then falls back to sending the bare reference rather than a link that
    cannot work.
    """
    if request is None:
        return ""
    from urllib.parse import urlencode

    from apps.schools.tenant_url import tenant_absolute_url

    school = getattr(request, "school", None) or getattr(
        getattr(consent, "membership", None), "school", None
    )
    url = tenant_absolute_url(
        request, "athletics:participation_consent_public", school=school
    )
    query = urlencode({"token": raw_token})
    return f"{url}?{query}"


def _send_consent_email(
    *, consent, guardian_email: str, raw_token: str, request=None
) -> None:
    """Best-effort transactional email carrying the one-time consent token.

    Wrapped by the caller in try/except; import failures / delivery failures
    must never fail the mint. Never logs the email or the token.

    The body carries a LINK, not a bare reference. It used to say 'Your one-time
    consent reference is: <token>' and stop there -- the consent pages exist and
    are reachable, so the guardian was handed a secret with nowhere to put it and
    the flow had no entry point at all.
    """
    from apps.schoolops.email_compat import send_mail

    subject = "Athletics participation consent requested"
    link = _consent_link(consent=consent, raw_token=raw_token, request=request)
    action = (
        f"Open this link to give or decline consent:\n{link}\n\n"
        if link
        else f"Your one-time consent reference is: {raw_token}\n\n"
    )
    body = (
        f"Hello {consent.guardian_name},\n\n"
        "You have been asked to give consent for a student's participation in "
        "a school sports team.\n\n"
        f"{action}"
        "This expires soon and can be used only once. If you did not expect this "
        "request you can safely ignore it."
    )
    send_mail(
        subject,
        body,
        None,  # from_email — reliability layer resolves the default sender
        [guardian_email],
        fail_silently=True,
    )


def request_participation_consent(
    *,
    membership,
    guardian_name: str,
    guardian_email: str,
    consent_text: str,
    version: str = CONSENT_TEXT_VERSION,
    request=None,
) -> str:
    """Mint a consent token for ``membership`` and email the guardian.

    Returns the raw token exactly once. Email is best-effort — a delivery or
    import failure is swallowed so it can never roll back the mint.
    """
    with transaction.atomic():
        raw_token, consent = ParticipationConsent.mint(
            membership=membership,
            guardian_name=guardian_name,
            guardian_email=guardian_email,
            consent_text=consent_text,
            consent_text_version=version,
        )

    try:
        _send_consent_email(
            consent=consent,
            guardian_email=guardian_email,
            raw_token=raw_token,
            request=request,
        )
    except Exception:  # noqa: BLE001 — email is best-effort; never fail the mint
        logger.warning(
            "participation_consent_email_failed consent=%s", consent.pk
        )

    return raw_token


def record_consent_decision(
    *, raw_token: str, consented: bool, request=None
) -> ParticipationConsent:
    """Apply a guardian's decision to the consent identified by ``raw_token``.

    Not wrapped in an outer ``transaction.atomic``: the model's ``consent`` /
    ``decline`` methods run their own atomic blocks AND deliberately perform the
    expiry save OUTSIDE that block so it survives the raise — an outer
    transaction would roll that expiry write back. Raises
    ``ParticipationConsentError`` on an unknown token.
    """
    consent = ParticipationConsent.lookup_by_raw_token(raw_token)
    if consent is None:
        raise ParticipationConsentError("consent token not found")

    if consented:
        consent.consent(request)
    else:
        consent.decline(request)
    return consent


__all__ = ["request_participation_consent", "record_consent_decision"]
