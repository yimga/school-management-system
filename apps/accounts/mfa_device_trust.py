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
import time

from django.conf import settings
from django.core import signing

DEVICE_TRUST_COOKIE = "mfa_device_trust"
_SALT = "apps.accounts.mfa_device_trust.v1"
_DEFAULT_MAX_DAYS = 30
_DEFAULT_TRUST_DAYS = 14
_DEFAULT_ALLOWED_DAYS = (1, 7, 14, 30)
_ABSOLUTE_MAX_DAYS = 30


def device_trust_max_days() -> int:
    """Platform cap for a trusted-device waiver (default and hard cap 30 days)."""
    raw = str(getattr(settings, "MFA_DEVICE_TRUST_DAYS", "") or "").strip()
    days = _DEFAULT_MAX_DAYS
    if raw:
        try:
            value = int(raw)
            if value > 0:
                days = min(value, _ABSOLUTE_MAX_DAYS)
        except ValueError:
            pass
    return days


def device_trust_allowed_days() -> tuple[int, ...]:
    """Selectable trust periods, constrained by the platform maximum."""
    raw = str(
        getattr(settings, "MFA_DEVICE_TRUST_ALLOWED_DAYS", "") or ""
    ).strip()
    values: list[int] = []
    candidates = raw.replace(",", " ").split() if raw else _DEFAULT_ALLOWED_DAYS
    for candidate in candidates:
        try:
            value = int(candidate)
        except (TypeError, ValueError):
            continue
        if (
            value in _DEFAULT_ALLOWED_DAYS
            and value <= device_trust_max_days()
            and value not in values
        ):
            values.append(value)
    if not values:
        values.append(device_trust_max_days())
    return tuple(sorted(values))


def device_trust_default_days() -> int:
    """Default selection, always one of :func:`device_trust_allowed_days`."""
    allowed = device_trust_allowed_days()
    raw = str(
        getattr(settings, "MFA_DEVICE_TRUST_DEFAULT_DAYS", "") or ""
    ).strip()
    try:
        requested = int(raw) if raw else _DEFAULT_TRUST_DAYS
    except ValueError:
        requested = _DEFAULT_TRUST_DAYS
    if requested in allowed:
        return requested
    return min(allowed, key=lambda value: abs(value - requested))


def normalize_device_trust_days(value) -> int:
    """Return an allowed trust period; arbitrary client values never extend it."""
    try:
        requested = int(value)
    except (TypeError, ValueError):
        requested = device_trust_default_days()
    allowed = device_trust_allowed_days()
    return requested if requested in allowed else device_trust_default_days()


def device_trust_opt_in(*, remember_flag=None, trust_days_value=None) -> bool:
    """True when the user asked to trust this browser (skip MFA on next login).

    The trust-PERIOD control is now the primary, self-sufficient switch: picking a
    real allowed period (1/7/14/30 days) arms trust on its own. This removes the old
    decoupling trap where the period dropdown was a SEPARATE control from a
    "remember this device" checkbox — a user who changed the day count but never
    ticked the box was silently NOT trusted, then re-prompted for MFA on the next
    login ("I set the days but it still asks me"). A "Don't trust" selection submits
    ``0`` / empty, which is not an allowed period, so it correctly does not opt in.

    The legacy ``remember_flag`` (checkbox / JSON boolean) is still honored for any
    caller that continues to post it, so no existing integration breaks.
    """
    if remember_flag in (True, "1", "true", "on", "yes"):
        return True
    try:
        picked = int(trust_days_value)
    except (TypeError, ValueError):
        return False
    return picked in device_trust_allowed_days()


def device_trust_max_age_seconds(days=None) -> int:
    """Trust lifetime in seconds.

    With no explicit period this returns the platform validation cap for
    backward-compatible cookies. New cookies always pass a selected period.
    """
    if days is None:
        days = device_trust_max_days()
    else:
        days = normalize_device_trust_days(days)
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


def issue_device_trust_token(user, *, trust_days=None) -> str:
    days = normalize_device_trust_days(trust_days)
    expires_at = int(time.time()) + device_trust_max_age_seconds(days)
    return signing.dumps(
        {
            "uid": str(getattr(user, "pk", "")),
            "fp": _fingerprint(user),
            "ver": int(getattr(user, "mfa_device_trust_version", 1) or 1),
            "days": days,
            "exp": expires_at,
        },
        salt=_SALT,
    )


def device_trust_valid(request, user) -> bool:
    """True when this request carries a valid, unexpired device-trust cookie for
    ``user`` (signed, right user, matching password fingerprint)."""
    if user is None or not getattr(user, "is_authenticated", False):
        return False
    if not getattr(user, "is_active", False):
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
    try:
        token_version = int(data.get("ver", 1))
        current_version = int(
            getattr(user, "mfa_device_trust_version", 1) or 1
        )
    except (TypeError, ValueError):
        return False
    if token_version != current_version:
        return False
    # New tokens carry their selected period. The signed absolute expiry makes
    # a 1/7/14-day choice real even though validation also accepts legacy tokens
    # up to the platform-wide maximum.
    if "exp" in data:
        try:
            expires_at = int(data["exp"])
            days = int(data.get("days"))
        except (TypeError, ValueError):
            return False
        if days not in device_trust_allowed_days():
            return False
        if int(time.time()) > expires_at:
            return False
    return True


def revoke_device_trust(user_or_id) -> bool:
    """Invalidate every trusted-browser token for one user, atomically."""
    user_id = getattr(user_or_id, "pk", user_or_id)
    if not user_id:
        return False
    from django.contrib.auth import get_user_model
    from django.db.models import F

    User = get_user_model()
    updated = User.objects.filter(pk=user_id).update(
        mfa_device_trust_version=F("mfa_device_trust_version") + 1
    )
    if updated and hasattr(user_or_id, "mfa_device_trust_version"):
        current = int(
            getattr(user_or_id, "mfa_device_trust_version", 1) or 1
        )
        user_or_id.mfa_device_trust_version = current + 1
    return bool(updated)


def set_device_trust_cookie(response, user, request, *, trust_days=None) -> None:
    """Attach the durable device-trust cookie to ``response`` (opt-in caller)."""
    days = normalize_device_trust_days(trust_days)
    secure = bool(getattr(settings, "SESSION_COOKIE_SECURE", False)) or bool(
        getattr(request, "is_secure", lambda: False)()
    )
    response.set_cookie(
        DEVICE_TRUST_COOKIE,
        issue_device_trust_token(user, trust_days=days),
        max_age=device_trust_max_age_seconds(days),
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
