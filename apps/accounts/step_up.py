"""Sudo-style step-up re-authentication for sensitive actions.

The tenant model is *one session*: an owner/admin logs in once and moves between
frontend and the config backend freely (see ``tenant_admin_required``). We do NOT
re-login per backend page — that is the anti-pattern the finance-lockout bug
exhibited. Instead, the genuinely destructive/financial actions (payment payout
setup, integration credentials, ownership transfer, data export, deleting a
school) sit behind a short, timed *step-up*: a fresh "confirm your identity"
(password + a fresh MFA code, for MFA users) that grants a brief elevation window
on the SAME session — the ``sudo`` model, not a new login.

This mirrors how the platforms we benchmark against work: Shopify/Salesforce/AWS
keep one session and re-verify only for sensitive actions; ``sudo`` elevates the
same shell for a timed window. The window here is settings-driven
(``STEP_UP_REAUTH_MAX_AGE_SECONDS``, default 10 min) and, when armed, also revives
the previously-dead ``pii_masking.set_pii_reauth`` window so full-PII display and
step-up share one "recently re-verified" clock.
"""

from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode

# Session key holding the unix timestamp of the last successful step-up.
STEP_UP_SESSION_KEY = "step_up_at"

_DEFAULT_MAX_AGE_SECONDS = 600  # magic-number-allow: step-up-reauth-window-ten-minutes


def step_up_max_age() -> int:
    """Elevation window length in seconds (settings-driven, fail-safe default)."""
    try:
        value = int(getattr(settings, "STEP_UP_REAUTH_MAX_AGE_SECONDS", _DEFAULT_MAX_AGE_SECONDS))
        return value if value > 0 else _DEFAULT_MAX_AGE_SECONDS
    except (TypeError, ValueError):
        return _DEFAULT_MAX_AGE_SECONDS


def mark_step_up(request) -> None:
    """Record a successful step-up on the current session (and revive PII display)."""
    session = getattr(request, "session", None)
    if session is None:
        return
    session[STEP_UP_SESSION_KEY] = int(timezone.now().timestamp())
    session.modified = True
    # Share the "recently re-verified" clock with PII display (was dead code).
    try:
        from apps.accounts.pii_masking import set_pii_reauth

        set_pii_reauth(request)
    except (ImportError, AttributeError):
        pass


def has_recent_step_up(request, max_age: int | None = None) -> bool:
    """True when this session stepped up within ``max_age`` seconds."""
    session = getattr(request, "session", None)
    if session is None:
        return False
    raw = session.get(STEP_UP_SESSION_KEY)
    if raw is None:
        return False
    try:
        stamped = int(raw)
    except (TypeError, ValueError):
        return False
    window = step_up_max_age() if max_age is None else max_age
    return (int(timezone.now().timestamp()) - stamped) <= window


def clear_step_up(request) -> None:
    """Drop any elevation (e.g. on logout / sensitive-context exit)."""
    session = getattr(request, "session", None)
    if session is None:
        return
    if STEP_UP_SESSION_KEY in session:
        del session[STEP_UP_SESSION_KEY]
        session.modified = True


def require_step_up(view_func=None, *, max_age: int | None = None):
    """Require a recent step-up; otherwise send the user to the re-auth challenge.

    Layer ABOVE ``tenant_admin_required`` (authorization first, then elevation):

        @tenant_admin_required
        @require_step_up()
        def payment_readiness_setup(request): ...

    Unauthenticated requests are left to the auth decorator beneath; this decorator
    only intercepts an authenticated session lacking a fresh elevation, redirecting
    to ``accounts:step_up`` with a sanitized ``next``.
    """

    def _decorate(fn):
        @wraps(fn)
        def _inner(request, *args, **kwargs):
            user = getattr(request, "user", None)
            if getattr(user, "is_authenticated", False) and not has_recent_step_up(
                request, max_age
            ):
                target = f"{reverse('accounts:step_up')}?{urlencode({'next': request.get_full_path()})}"
                return redirect(target)
            return fn(request, *args, **kwargs)

        return _inner

    if view_func is not None and callable(view_func):
        return _decorate(view_func)
    return _decorate
