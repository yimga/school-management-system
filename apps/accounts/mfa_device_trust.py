"""Durable "trust this device" cookie for MFA.

A signed, HTTP-only cookie that records a browser passed MFA, so the user is not
re-prompted for their code on a *fresh* session — a pin flush, a re-login, or a
session expiry — within the trust window. It lives OUTSIDE the server session, so
it survives a session reset; that reset (losing ``session['mfa_verified']``) is
the mechanism behind the "constantly asked for MFA" reports.

Security properties:

* Signed with ``SECRET_KEY`` (``django.core.signing``) — a client can't forge it.
* Bound to the user's ``get_session_auth_hash()`` fingerprint, so a password
  change (or Django's "log out of other sessions") invalidates every device-trust
  cookie the user holds — same revocation lever Django uses for sessions.
* ``HttpOnly`` + ``Secure`` (when the request is HTTPS) + ``SameSite=Lax``.
* Opt-in: only issued when the user ticks "remember this device", so a shared
  computer is never silently trusted.
"""
from __future__ import annotations

import hashlib
import os

from django.conf import settings
from django.core import signing

DEVICE_TRUST_COOKIE = "mfa_device_trust"
_SALT = "apps.accounts.mfa_device_trust.v1"
_DEFAULT_DAYS = 30


def device_trust_max_age_seconds() -> int:
    """Trust window in seconds (``MFA_DEVICE_TRUST_DAYS`` env, default 30 days)."""
    raw = (os.getenv("MFA_DEVICE_TRUST_DAYS", "") or "").strip()
    days = _DEFAULT_DAYS
    if raw:
        try:
            value = int(raw)
            if value > 0:
                days = value
        except ValueError:
            pass
    return days * 24 * 60 * 60


def _device_trust_cookie_domain():
    """Cookie ``domain`` — aligned with the session cookie, never broader.

    The session cookie is scoped to the parent domain in production
    (``SESSION_COOKIE_DOMAIN = ".runmycampus.com"`` in render.yaml) so login
    carries across every tenant subdomain. Without matching that here, the
    device-trust cookie is HOST-ONLY: an owner who ticks "remember this device"
    while enrolling on the base/public host gets a cookie that is simply absent
    on their tenant subdomain — so the durability guarantee this module exists to
    provide ("survives a session reset") silently fails the moment they cross
    hosts, and they are re-challenged for MFA on the very tenant they just set up.

    Scoping the trust cookie to exactly the session's domain (``None`` in dev,
    where it is unset) keeps it no broader than the session it backs.
    """
    return getattr(settings, "SESSION_COOKIE_DOMAIN", None) or None


def _fingerprint(user) -> str:
    """Short digest that changes when the user's password changes (revocation).

    Uses Django's ``get_session_auth_hash`` (HMAC of the password field) so a
    password reset or "log out everywhere" rotates it and every outstanding
    device-trust cookie stops validating.
    """
    try:
        base = user.get_session_auth_hash()
    except Exception:  # noqa: BLE001 — degrade to pk so a broken hash never trusts widely
        base = str(getattr(user, "pk", ""))
    return hashlib.sha256((base or "").encode("utf-8")).hexdigest()[:16]


def issue_device_trust_token(user) -> str:
    return signing.dumps(
        {"uid": str(getattr(user, "pk", "")), "fp": _fingerprint(user)},
        salt=_SALT,
    )


def device_trust_valid(request, user) -> bool:
    """True when this request carries a valid, unexpired device-trust cookie for
    ``user`` (signed, right user, matching password fingerprint)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    raw = request.COOKIES.get(DEVICE_TRUST_COOKIE)
    if not raw:
        return False
    try:
        data = signing.loads(raw, salt=_SALT, max_age=device_trust_max_age_seconds())
    except (signing.BadSignature, signing.SignatureExpired):
        return False
    if not isinstance(data, dict):
        return False
    if str(data.get("uid")) != str(getattr(user, "pk", "")):
        return False
    if data.get("fp") != _fingerprint(user):
        return False
    return True


def set_device_trust_cookie(response, user, request) -> None:
    """Attach the durable device-trust cookie to ``response`` (opt-in caller)."""
    secure = bool(getattr(settings, "SESSION_COOKIE_SECURE", False)) or bool(
        getattr(request, "is_secure", lambda: False)()
    )
    response.set_cookie(
        DEVICE_TRUST_COOKIE,
        issue_device_trust_token(user),
        max_age=device_trust_max_age_seconds(),
        domain=_device_trust_cookie_domain(),
        httponly=True,
        secure=secure,
        samesite="Lax",
    )


def clear_device_trust_cookie(response) -> None:
    """Drop the device-trust cookie (e.g. on 'log out of all devices').

    Must pass the same ``domain`` used to set it — ``delete_cookie`` only clears
    a domain-scoped cookie when the domain matches, otherwise the trust survives
    a "log out of all devices".
    """
    response.delete_cookie(DEVICE_TRUST_COOKIE, domain=_device_trust_cookie_domain())
