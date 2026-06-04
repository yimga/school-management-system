"""Pillar 3 — Verified Communications: DKIM email signing posture.

Without DKIM (DomainKeys Identified Mail) signing on outbound email, a
scammer can forge ``From: principal@<school>.edu`` and trick parents
into wiring tuition to a fraudulent account. Receiving servers cannot
distinguish the spoof from a genuine school email unless every legit
message carries a DKIM signature whose public key resolves through the
school's DNS.

DKIM signing itself is **provider-side** — the upstream ESP (Mailgun,
SendGrid, Postmark, Mailjet, Amazon SES, …) signs the headers with the
private key it manages and the school publishes the matching ``TXT``
record at ``<selector>._domainkey.<school-domain>``. This module's job
is therefore not to sign mail but to:

1. **Detect** which Django email backend the platform is wired to.
2. **Classify** that backend as DKIM-signing or not.
3. **Report** the posture (CLI + dashboard + AppConfig.ready hook).
4. **Gate** deployment: when ``EMAIL_SIGNING_REQUIRED=True`` (production
   posture) the ready hook raises if the backend is the console / smtp
   default, so the deploy fails loudly rather than shipping spoofable
   transactional email.

DNS records the operator must publish on every tenant domain that
sends mail:

* ``<selector>._domainkey.<domain>`` ``TXT`` — DKIM public key
  (selector chosen by the ESP; e.g. ``mg`` for Mailgun, ``s1`` for
  SendGrid).
* ``_dmarc.<domain>`` ``TXT`` — DMARC policy. Start at ``p=none`` to
  observe, escalate to ``p=quarantine`` then ``p=reject`` once aligned.
* ``<domain>`` ``TXT`` — SPF record listing the ESP's sending IPs
  (``v=spf1 include:mailgun.org -all`` for Mailgun, etc.).

DKIM alone protects header authenticity; DMARC + SPF close the
envelope-from gap. The platform's responsibility ends at provider
selection + DNS guidance; this module surfaces the state of the
former so the latter can be enforced operationally.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


# Anymail backends that route through a DKIM-signing ESP. The presence
# of the backend string is sufficient signal that the platform is
# outsourcing signing to a provider that signs by default once the DNS
# records resolve — we don't second-guess provider config here, that's
# the operator's runbook (verify the public key resolves at
# ``<selector>._domainkey.<domain>`` after DNS propagation).
DKIM_SIGNING_BACKENDS: dict[str, str] = {
    "anymail.backends.mailgun.EmailBackend": "Mailgun",
    "anymail.backends.sendgrid.EmailBackend": "SendGrid",
    "anymail.backends.postmark.EmailBackend": "Postmark",
    "anymail.backends.mailjet.EmailBackend": "Mailjet",
    "anymail.backends.amazon_ses.EmailBackend": "Amazon SES",
    "anymail.backends.sparkpost.EmailBackend": "SparkPost",
    "anymail.backends.mandrill.EmailBackend": "Mandrill",
    "anymail.backends.mailersend.EmailBackend": "MailerSend",
    "anymail.backends.sendinblue.EmailBackend": "Sendinblue / Brevo",
    "anymail.backends.brevo.EmailBackend": "Brevo",
    "anymail.backends.resend.EmailBackend": "Resend",
}

# Backends that DO NOT sign — useful for development but unsafe in
# production. The console backend just prints to stdout; the smtp
# backend ships raw to whatever relay the operator points it at and
# relies on that relay to sign (which the platform cannot verify).
NON_SIGNING_BACKENDS: dict[str, str] = {
    "django.core.mail.backends.console.EmailBackend": "Django console (dev)",
    "django.core.mail.backends.locmem.EmailBackend": "Django locmem (test)",
    "django.core.mail.backends.dummy.EmailBackend": "Django dummy",
    "django.core.mail.backends.filebased.EmailBackend": "Django file-based (dev)",
    "django.core.mail.backends.smtp.EmailBackend": "Django SMTP (relay-dependent)",
}


# SMTP relays that sign DKIM at the relay edge. When the plain Django SMTP
# backend points at one of these, mail IS DKIM-signed even though the backend
# itself is "relay-dependent" (audit H13 — the classifier false-negatived the
# production Brevo relay and could hard-block a correctly-signed deploy).
_KNOWN_SIGNING_SMTP_RELAYS: dict[str, str] = {
    "smtp-relay.brevo.com": "Brevo (SMTP relay)",
    "smtp-relay.sendinblue.com": "Brevo / Sendinblue (SMTP relay)",
    "smtp.sendgrid.net": "SendGrid (SMTP relay)",
    "smtp.mailgun.org": "Mailgun (SMTP relay)",
    "smtp.postmarkapp.com": "Postmark (SMTP relay)",
    "email-smtp.us-east-1.amazonaws.com": "Amazon SES (SMTP relay)",
    "smtp.resend.com": "Resend (SMTP relay)",
}


def _configured_backend() -> str:
    """Resolve the EMAIL_BACKEND string from settings (never raises)."""
    return str(getattr(settings, "EMAIL_BACKEND", "") or "")


def _signing_smtp_relay() -> str:
    """Return a provider name when EMAIL_HOST is a known DKIM-signing relay.

    Honors an explicit operator override list via
    ``EMAIL_DKIM_RELAY_TRUSTED`` (comma-separated hostnames)."""
    host = str(getattr(settings, "EMAIL_HOST", "") or "").strip().lower()
    if not host:
        return ""
    if host in _KNOWN_SIGNING_SMTP_RELAYS:
        return _KNOWN_SIGNING_SMTP_RELAYS[host]
    trusted = str(getattr(settings, "EMAIL_DKIM_RELAY_TRUSTED", "") or "")
    trusted_hosts = {h.strip().lower() for h in trusted.split(",") if h.strip()}
    if host in trusted_hosts:
        return f"{host} (operator-trusted SMTP relay)"
    return ""


def email_signing_status() -> dict[str, Any]:
    """Return a structured report of the platform's DKIM posture.

    Shape mirrors ``apps.security.csp_readiness.assess_csp_readiness``:
    a plain dict the security-readiness dashboard / CLI / tests all
    consume.

    Keys:
      backend         — dotted EMAIL_BACKEND path.
      signs_dkim      — True iff the backend routes through a known
                        DKIM-signing ESP.
      provider        — human-readable provider name (e.g. "Mailgun")
                        or a descriptor for non-signing backends.
      required        — value of EMAIL_SIGNING_REQUIRED (production
                        posture flag).
      default_from    — the platform's DEFAULT_FROM_EMAIL, included so
                        the dashboard can surface which domain the
                        operator must publish DNS records for.
    """
    backend = _configured_backend()
    signs_dkim = backend in DKIM_SIGNING_BACKENDS
    relay_provider = ""
    if signs_dkim:
        provider = DKIM_SIGNING_BACKENDS[backend]
    elif backend in NON_SIGNING_BACKENDS:
        # Only the real SMTP backend actually ships through EMAIL_HOST, so the
        # relay-signs-DKIM inference applies to it alone. The console / locmem /
        # dummy / filebased backends never send mail — a configured EMAIL_HOST
        # (e.g. a dev .env still pointing at Brevo) must NOT make them report
        # signed (audit H13 follow-up: this previously false-positived the
        # console backend whenever EMAIL_HOST happened to be a known relay).
        if backend == "django.core.mail.backends.smtp.EmailBackend":
            relay_provider = _signing_smtp_relay()
        if relay_provider:
            signs_dkim = True
            provider = relay_provider
        else:
            provider = NON_SIGNING_BACKENDS[backend]
    else:
        provider = "Unknown backend"

    return {
        "backend": backend,
        "signs_dkim": signs_dkim,
        "provider": provider,
        "required": bool(getattr(settings, "EMAIL_SIGNING_REQUIRED", False)),
        "default_from": str(getattr(settings, "DEFAULT_FROM_EMAIL", "") or ""),
    }


class EmailSigningMisconfigured(RuntimeError):
    """Raised at startup when EMAIL_SIGNING_REQUIRED=True but no signing backend is wired."""


def assert_dkim_configured() -> dict[str, Any]:
    """Startup gate for the AppConfig.ready hook.

    Returns the status dict (so callers / tests can inspect it).

    Behavior:
      * Signing backend wired → log INFO, return status.
      * Non-signing backend + EMAIL_SIGNING_REQUIRED=True → raise
        ``EmailSigningMisconfigured`` so deploy fails loudly.
      * Non-signing backend + EMAIL_SIGNING_REQUIRED=False →
        ``logger.warning`` with remediation hint (soft-warn in dev).
    """
    status = email_signing_status()
    backend = status["backend"]
    provider = status["provider"]

    if status["signs_dkim"]:
        logger.info(
            "email signing: backend=%s provider=%s — DKIM signing handled provider-side.",
            backend,
            provider,
        )
        return status

    msg = (
        f"email signing: backend={backend!r} does NOT sign DKIM "
        f"({provider}). Outbound mail is spoofable. Switch to an "
        f"anymail backend (Mailgun / SendGrid / Postmark / SES / ...) "
        f"and publish DKIM + SPF + DMARC TXT records on the sending "
        f"domain."
    )

    if status["required"]:
        raise EmailSigningMisconfigured(msg)

    # Render predeploy runs many management commands; console backend without
    # anymail is an acknowledged staging posture until ESP DNS is wired.
    render_hosted = os.getenv("RENDER", "").strip().lower() == "true"
    silence_console = os.getenv(
        "EMAIL_SIGNING_SILENCE_CONSOLE_WARN", ""
    ).strip().lower() in ("1", "true", "yes")
    if render_hosted or silence_console:
        logger.debug(msg)
    else:
        logger.warning(msg)
    return status


__all__ = [
    "DKIM_SIGNING_BACKENDS",
    "NON_SIGNING_BACKENDS",
    "EmailSigningMisconfigured",
    "assert_dkim_configured",
    "email_signing_status",
]
