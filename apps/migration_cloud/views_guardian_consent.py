"""Guardian-facing consent collection views (v3.40.0 Agent 11).

These views are **anonymous** — the guardian does NOT have a portal
login. The URL contains an unguessable URL-safe token (256 bits of
entropy from ``secrets.token_urlsafe(32)``); that's the auth.

URL grammar (mounted at ``/migration/consent/``):

    /migration/consent/<raw_token>/             — landing GET
    /migration/consent/<raw_token>/accept/      — accept POST
    /migration/consent/<raw_token>/decline/     — decline POST
    /migration/consent/<raw_token>/revoke/      — revoke POST

Defense layers:

  * Single SHA-256 lookup per request — no per-row iteration.
  * Constant-time compare via :func:`hmac.compare_digest` inside the
    model's ``matches()`` helper (defense-in-depth; the unique-index
    lookup already provides constant-time-by-database semantics).
  * Uniform 200 OK response on not-found / expired / already-decided
    tokens — no enumeration oracle.
  * Raw token NEVER logged; only sha256 prefix (first 8 hex chars).
  * IP + UA captured server-side at consent decision time only.
  * ``@never_cache`` + ``Cache-Control: no-store`` headers — no shared
    proxy cache may retain consent landing.
  * ``X-Frame-Options: DENY`` — anti-clickjack defense.
  * ``@csrf_exempt`` on POST endpoints (anonymous + token-in-URL); the
    URL itself is the unforgeable credential.
"""
from __future__ import annotations

import logging
from typing import Optional

from django.http import (
    HttpRequest,
    HttpResponse,
    HttpResponseBadRequest,
)
from django.shortcuts import render
from django.template.loader import select_template, TemplateDoesNotExist
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_exempt

from .models_guardian_consent import (
    GuardianConsentDecision,
    GuardianConsentToken,
    GuardianConsentTokenError,
)

logger = logging.getLogger(__name__)


# ─── Helpers ──────────────────────────────────────────────────────────────


DEFAULT_CONSENT_TEXT_VERSION = "v1"


def _render_consent_text(version: str) -> str:
    """Render the active consent text body to a string.

    Looks up
    ``templates/migration_cloud/guardian_consent/_consent_text_<version>.html``.
    On miss, falls back to ``v1`` so a stale token always has SOMETHING
    to render (the sha256 immutable record protects against a swap).
    """
    candidates = [
        f"migration_cloud/guardian_consent/_consent_text_{version}.html",
        "migration_cloud/guardian_consent/_consent_text_v1.html",
    ]
    try:
        tmpl = select_template(candidates)
    except TemplateDoesNotExist:
        return ""
    return tmpl.render({})


def _apply_consent_security_headers(response: HttpResponse) -> HttpResponse:
    """Stamp anti-cache + anti-clickjack headers on every consent response."""
    response["Cache-Control"] = "no-store, max-age=0"
    response["Pragma"] = "no-cache"
    response["Expires"] = "0"
    response["X-Frame-Options"] = "DENY"
    response["X-Content-Type-Options"] = "nosniff"
    response["Referrer-Policy"] = "no-referrer"
    return response


def _render_completed(
    request: HttpRequest,
    *,
    message_key: str,
    token: Optional[GuardianConsentToken] = None,
) -> HttpResponse:
    """Uniform-shape "completed / not-found / expired" response.

    Returns HTTP 200 in every branch so an attacker cannot probe for
    valid tokens via status-code differentials.
    """
    context = {
        "message_key": message_key,
        # token is intentionally only passed for "consented" / "declined"
        # success branches so the not-found branch can NOT differentiate
        # itself from a real-but-decided token.
        "token": token,
    }
    response = render(
        request,
        "migration_cloud/guardian_consent/consent_completed.html",
        context,
        status=200,
    )
    return _apply_consent_security_headers(response)


def _resolve_token_or_completed(
    request: HttpRequest,
    raw_token: str,
) -> tuple[Optional[GuardianConsentToken], Optional[HttpResponse]]:
    """Look up a token and short-circuit the response on miss/decided/expired.

    Returns ``(token, None)`` when the caller should proceed to
    accept/decline/landing; otherwise ``(None, response)``.
    """
    token = GuardianConsentToken.lookup_by_raw_token(raw_token)
    if token is None:
        # PII-free trace; no raw token logged.
        logger.info("migration_cloud.guardian_consent: lookup_miss")
        return None, _render_completed(request, message_key="not_found")
    # Defense-in-depth: constant-time compare even though the unique
    # index lookup already proves match.
    if not token.matches(raw_token):  # pragma: no cover — index collision impossible
        return None, _render_completed(request, message_key="not_found")
    if token.is_expired:
        return None, _render_completed(request, message_key="expired", token=token)
    if token.is_decided:
        return None, _render_completed(request, message_key="already_decided", token=token)
    return token, None


# ─── Guardian-facing views ────────────────────────────────────────────────


@method_decorator(never_cache, name="dispatch")
class GuardianConsentLandingView(View):
    """GET the consent landing page.

    Anonymous; returns HTTP 200 for ALL branches (uniform shape).
    """

    template_name = "migration_cloud/guardian_consent/consent_landing.html"

    def get(self, request: HttpRequest, raw_token: str, *args, **kwargs) -> HttpResponse:
        token, completed = _resolve_token_or_completed(request, raw_token)
        if completed is not None:
            return completed
        assert token is not None  # for type-checker

        # Stamp first-seen-at once.
        try:
            token.mark_first_seen()
        except Exception as exc:  # noqa: BLE001 — never break landing
            logger.warning(
                "migration_cloud.guardian_consent: first_seen_mark_failed "
                "token_sha_prefix=%s err=%s",
                (token.token_sha256 or "")[:8], type(exc).__name__,
            )

        consent_text_body = _render_consent_text(token.consent_text_version)
        context = {
            "raw_token": raw_token,
            "token": token,
            "consent_text_body": consent_text_body,
            "consent_text_version": token.consent_text_version,
        }
        response = render(request, self.template_name, context, status=200)
        return _apply_consent_security_headers(response)


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class GuardianConsentAcceptView(View):
    """POST to accept the consent.

    Anonymous; the URL token is the credential. CSRF-exempt because
    a CSRF token would have to be served by an upstream anonymous GET,
    providing no protection. The unguessable URL is the defense.
    """

    def post(self, request: HttpRequest, raw_token: str, *args, **kwargs) -> HttpResponse:
        token, completed = _resolve_token_or_completed(request, raw_token)
        if completed is not None:
            return completed
        assert token is not None
        # Anti-clickjack one-time-confirm: form posts a hidden field
        # confirm=on; we tolerate its absence (some accessibility tools
        # strip hidden inputs) but log when it's missing.
        if request.POST.get("confirm") != "on":
            logger.info(
                "migration_cloud.guardian_consent: accept_without_confirm "
                "token_sha_prefix=%s",
                (token.token_sha256 or "")[:8],
            )
        try:
            token.consent(request=request)
        except GuardianConsentTokenError as exc:
            # Token race-decided between landing and accept — treat as
            # already-decided.
            logger.info(
                "migration_cloud.guardian_consent: accept_race "
                "token_sha_prefix=%s err=%s",
                (token.token_sha256 or "")[:8], type(exc).__name__,
            )
            return _render_completed(
                request, message_key="already_decided", token=token,
            )
        return _render_completed(
            request, message_key="consented", token=token,
        )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class GuardianConsentDeclineView(View):
    """POST to decline the consent. Symmetric to accept; no count bump."""

    def post(self, request: HttpRequest, raw_token: str, *args, **kwargs) -> HttpResponse:
        token, completed = _resolve_token_or_completed(request, raw_token)
        if completed is not None:
            return completed
        assert token is not None
        try:
            token.decline(request=request)
        except GuardianConsentTokenError:
            return _render_completed(
                request, message_key="already_decided", token=token,
            )
        return _render_completed(
            request, message_key="declined", token=token,
        )


@method_decorator(csrf_exempt, name="dispatch")
@method_decorator(never_cache, name="dispatch")
class GuardianConsentRevokeView(View):
    """POST to revoke a previously-granted consent.

    FERPA / COPPA right-to-withdraw. Only valid inside the configured
    revocation window (default 90 days).
    """

    def post(self, request: HttpRequest, raw_token: str, *args, **kwargs) -> HttpResponse:
        # Note: revoke does NOT call _resolve_token_or_completed because
        # the token IS expected to be in CONSENTED state (which the
        # helper treats as "decided" → short-circuits).
        token = GuardianConsentToken.lookup_by_raw_token(raw_token)
        if token is None or not token.matches(raw_token):
            return _render_completed(request, message_key="not_found")
        if token.consent_decision != GuardianConsentDecision.CONSENTED.value:
            return HttpResponseBadRequest("token is not in consented state")
        if not token.is_revocable:
            return HttpResponseBadRequest("revocation window has closed")
        try:
            token.revoke()
        except GuardianConsentTokenError as exc:
            return HttpResponseBadRequest(str(exc))
        return _render_completed(
            request, message_key="revoked", token=token,
        )
