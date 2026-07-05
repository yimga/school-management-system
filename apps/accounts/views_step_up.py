"""Step-up re-authentication challenge ("confirm your identity to continue").

Renders on the SAME session — this is elevation, not a new login. Verifies the
user's password and, for MFA-enrolled users, a fresh second factor (TOTP or a
backup code), then arms the short step-up window via ``step_up.mark_step_up``.
"""

from __future__ import annotations

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.accounts.step_up import mark_step_up, step_up_max_age


def _safe_next(request) -> str:
    """Return a same-host relative ``next`` or a safe default (prevents open redirect)."""
    candidate = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if candidate and url_has_allowed_host_and_scheme(
        candidate,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return candidate
    return "/"


def _user_has_mfa(user) -> bool:
    try:
        from django_otp import user_has_device

        return bool(user_has_device(user, confirmed=True))
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


def _verify_second_factor(user, token: str) -> bool:
    """Verify a fresh TOTP token or one-time backup code against the user's devices."""
    token = (token or "").strip()
    if not token:
        return False
    try:
        from django_otp import match_token

        return match_token(user, token) is not None
    except (ImportError, AttributeError, TypeError, ValueError):
        return False


@login_required
@require_http_methods(["GET", "POST"])
def step_up_challenge(request):
    next_url = _safe_next(request)
    has_mfa = _user_has_mfa(request.user)
    error = ""

    if request.method == "POST":
        password = request.POST.get("password") or ""
        token = request.POST.get("otp_token") or ""
        password_ok = bool(password) and request.user.check_password(password)
        if not password_ok:
            error = _("That password is incorrect. Please try again.")
        elif has_mfa and not _verify_second_factor(request.user, token):
            error = _("Enter a current code from your authenticator (or a backup code).")
        else:
            mark_step_up(request)
            return redirect(next_url)

    context = {
        "next": next_url,
        "has_mfa": has_mfa,
        "error": error,
        "window_minutes": max(1, step_up_max_age() // 60),
    }
    return render(request, "auth/step_up_challenge.html", context)
