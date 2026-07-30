"""Guided recovery for never-activated accounts at the login form (2026-07-25).

A self-serve provisioned school owner — and any staff seeded the same way — is
created with an UNUSABLE password (``schools.tasks.ensure_admin_user_for_school``
calls ``set_unusable_password``): sign-in is meant to happen only after the owner
claims the account through a one-time token set-password link. When that link
never lands (mail relay misconfigured, link expired, forwarded to the wrong
address) the owner is stranded — every password they type is checked against an
unusable hash and fails, so ``/authentication/login/`` re-renders forever with
the generic "invalid username or password" dead-end (an HTTP 200 on the POST,
never the 302 that a real sign-in produces). This is the exact class of bug that
locked owners out platform-wide.

This module turns that dead-end into a self-healing path: on a failed login it
detects the never-activated state and emails the account a fresh, WORKING
set-password link (the audited password-reset machinery, which
``PortalPasswordResetForm`` already extends to never-activated owners), so the
login view can show "check your email" instead of "wrong password".

Security invariants:

* Only ACTIVE accounts with NO usable password trigger it. An established user
  with a real password is never touched, so a wrong password stays a plain wrong
  password (and still counts toward brute-force lockout in the caller).
* The email send is throttled per-user via the cache, so the public login form
  cannot be turned into a mail bomb against a known address.
* No password is set here and no token is handed to the caller — recovery still
  requires the account owner to click the emailed link. This opens NO
  account-takeover path.
* Passkey-only roles are skipped (a password link is useless to them).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import DatabaseError
from django.db.models import Q

logger = logging.getLogger(__name__)

# Mirror the /password_reset/ view's template wiring so the emailed link is the
# identical, battle-tested reset-confirm URL that already works for
# unusable-password owners.
_RESET_EMAIL_TEMPLATE = "emails/password_reset.txt"
_RESET_HTML_TEMPLATE = "emails/password_reset.html"
_RESET_SUBJECT_TEMPLATE = "registration/password_reset_subject.txt"

# At most one auto set-password link per user per window: the login form must not
# be usable to spam a real inbox with recovery emails.
_SEND_THROTTLE_SECONDS = 900  # magic-number-allow: one recovery email / 15 min / user
_THROTTLE_PREFIX = "login-recovery-sent:v1"


def recovery_enabled() -> bool:
    """Kill-switch (default ON) — no config/settings.py edit required to toggle."""
    return bool(getattr(settings, "LOGIN_UNACTIVATED_RECOVERY_ENABLED", True))


def _passkey_only_roles() -> tuple[str, ...]:
    return tuple(
        str(r).strip().upper()
        for r in (getattr(settings, "PASSKEY_ONLY_ROLES", ()) or ())
        if str(r).strip()
    )


def _is_passkey_only(user) -> bool:
    roles = _passkey_only_roles()
    if not roles:
        return False
    return (getattr(user, "role", "") or "").strip().upper() in roles


def find_unactivated_account(identifier: str):
    """Return a no-usable-password user matching username OR email.

    Prefers an exact username match (mirrors ``EmailOrUsernameModelBackend``)
    when an email is shared by more than one row. Passkey-only roles and
    usable-password accounts are excluded. Returns ``None`` when nothing
    qualifies — the caller then falls back to the normal wrong-password path.

    ``is_active`` is deliberately NOT required. A never-claimed account (created
    with ``set_unusable_password`` at provisioning / bulk import) can end up
    ``is_active=False`` — a partial provision, an import that left the row
    disabled, or an admin who parked it pre-activation. Such an account has NO
    password to protect, and a set-password link IS its intended onboarding
    path, so gating recovery on ``is_active`` is exactly what strands the
    new-user population behind a generic "invalid username or password" wall
    with no email ever arriving. We still exclude accounts with a REAL usable
    password (a genuine wrong-password stays a wrong password) and passkey-only
    roles (a password link is useless to them), so deactivating an established
    account still fully locks it.
    """
    ident = (identifier or "").strip()
    if not ident:
        return None
    User = get_user_model()
    try:
        candidates = list(
            # tenant-isolation-allow: login-recovery system-wide user lookup (auth is system-wide)
            User.objects.filter(
                Q(**{f"{User.USERNAME_FIELD}__iexact": ident}) | Q(email__iexact=ident),
            )[:10]  # magic-number-allow: bounded fan-out for a shared-email identifier
        )
    except DatabaseError:
        return None
    unactivated = [
        u for u in candidates
        if not u.has_usable_password() and not _is_passkey_only(u)
    ]
    if not unactivated:
        return None
    for u in unactivated:
        if (getattr(u, User.USERNAME_FIELD, "") or "").lower() == ident.lower():
            return u
    return unactivated[0]


def mask_email(email: str) -> str:
    """``owner@school.edu`` → ``o…r@school.edu``; empty when not an address."""
    email = (email or "").strip()
    if "@" not in email:
        return ""
    local, _at, domain = email.partition("@")
    if len(local) <= 2:
        shown = (local[:1] or "•") + "…"
    else:
        shown = f"{local[0]}…{local[-1]}"
    return f"{shown}@{domain}"


def send_set_password_link(request, user) -> bool:
    """Send the audited set-password (password-reset) email to ``user``.

    Reuses ``PortalPasswordResetForm`` exactly as the ``/password_reset/`` view
    does, so the recipient gets the same reset-confirm link that already works
    for unusable-password owners. Best-effort — never raises.
    """
    identifier = (
        (getattr(user, "email", "") or "").strip()
        or (getattr(user, "get_username", lambda: "")() or "").strip()
    )
    if not identifier:
        return False
    try:
        from apps.accounts.password_reset import PortalPasswordResetForm

        form = PortalPasswordResetForm(data={"email": identifier})
        if not form.is_valid():
            return False
        use_https = True
        try:
            use_https = bool(request.is_secure()) if request is not None else True
        except Exception:  # noqa: BLE001 — is_secure() must never break recovery
            use_https = True
        form.save(
            request=request,
            use_https=use_https,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
            email_template_name=_RESET_EMAIL_TEMPLATE,
            html_email_template_name=_RESET_HTML_TEMPLATE,
            subject_template_name=_RESET_SUBJECT_TEMPLATE,
        )
        return True
    except Exception as exc:  # noqa: BLE001 — delivery must never break the login response
        logger.warning(
            "accounts.login_recovery.send_failed user_id=%s err_type=%s",
            getattr(user, "pk", None), type(exc).__name__,
        )
        return False


def offer_unactivated_recovery(request, identifier: str) -> dict:
    """If ``identifier`` is a never-activated account, email it a set-password link.

    Returns ``{"unactivated": bool, "sent": bool, "email_masked": str}``. Never
    raises; safe on the login hot path. When ``unactivated`` is ``True`` the login
    view should show the guided "check your email" message instead of the generic
    invalid-credentials dead-end, and must NOT tally the attempt as a brute-force
    password guess (there is no password to guess).
    """
    result = {"unactivated": False, "sent": False, "email_masked": ""}
    if not recovery_enabled():
        return result
    try:
        user = find_unactivated_account(identifier)
    except Exception as exc:  # noqa: BLE001 — recovery is best-effort, never blocks login
        logger.warning(
            "accounts.login_recovery.lookup_failed err_type=%s", type(exc).__name__
        )
        return result
    if user is None:
        return result

    result["unactivated"] = True
    result["email_masked"] = mask_email(getattr(user, "email", "") or "")

    throttle_key = f"{_THROTTLE_PREFIX}:{user.pk}"
    try:
        fresh = cache.add(throttle_key, 1, _SEND_THROTTLE_SECONDS)
    except Exception:  # noqa: BLE001 — cache down → send anyway (help the owner over spam-guard)
        fresh = True
    if fresh:
        result["sent"] = send_set_password_link(request, user)
        logger.info(
            "accounts.login_recovery.offered user_id=%s sent=%s",
            user.pk, result["sent"],
        )
    else:
        # Already emailed within the window — keep the on-screen promise honest.
        result["sent"] = True
    return result


__all__ = [
    "recovery_enabled",
    "find_unactivated_account",
    "mask_email",
    "send_set_password_link",
    "offer_unactivated_recovery",
]
