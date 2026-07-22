"""Post-password MFA routing — shared by login_view and handoff callers.

Keeps password → MFA → destination as one contract so manager/public handoff
cannot skip the MFA challenge (symptom: password “buffers” then returns to
the sign-in page, or lands on backend with MFA never shown).
"""

from __future__ import annotations

from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone


def _mfa_remembered(request) -> bool:
    until_raw = request.session.get("mfa_verified_until")
    if not until_raw:
        return False
    try:
        until_dt = timezone.datetime.fromisoformat(until_raw)
        if timezone.is_naive(until_dt):
            until_dt = timezone.make_aware(until_dt, timezone.get_current_timezone())
        if timezone.now() <= until_dt:
            return True
    except (TypeError, ValueError):
        pass
    request.session.pop("mfa_verified_until", None)
    return False


def _user_has_mfa_device(user) -> bool:
    """TOTP (confirmed) or passkey — same surface RequireMFAMiddleware uses."""
    try:
        from django_otp import user_has_device
        from django_otp.plugins.otp_totp.models import TOTPDevice

        try:
            if user_has_device(user, confirmed=True):
                return True
        except TypeError:
            if user_has_device(user):
                return True
        if TOTPDevice.objects.filter(user=user, confirmed=True).exists():
            return True
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    try:
        from apps.accounts.models import UserPasskey

        if UserPasskey.objects.filter(user=user).exists():
            return True
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    return False


def _user_must_have_mfa(request, user) -> bool:
    """Match RequireMFAMiddleware: tenant config ∪ operator policy ∪ baseline floor."""
    try:
        from apps.accounts.mfa_defaults import (
            effective_required_roles,
            resolve_operator_mfa,
        )
        from apps.accounts.utils import get_user_role
        from apps.platform_runtime.config_resolver import get_effective_config

        require_all_staff = bool(
            get_effective_config(
                key="require_mfa_all_staff", request=request, default=False
            )
        )
        required_roles = (
            get_effective_config(key="require_mfa_roles", request=request) or []
        )
        operator_policy = resolve_operator_mfa(
            getattr(request, "school", None), request=request
        )
        if (require_all_staff or operator_policy.require_all_staff) and getattr(
            user, "is_staff", False
        ):
            return True
        role = get_user_role(user, getattr(request, "school", None))
        required_normalized = effective_required_roles(
            required_roles, operator_required=operator_policy.required_roles
        )
        if role and str(role).strip().upper() in required_normalized:
            return True
    except (ImportError, AttributeError, TypeError, ValueError):
        # Floor: ADMIN / baseline still enforced when config is unavailable.
        try:
            from apps.accounts.mfa_defaults import BASELINE_REQUIRED_ROLES

            role = (getattr(user, "role", "") or "").strip().upper()
            if role in {r.upper() for r in BASELINE_REQUIRED_ROLES}:
                return True
        except ImportError:
            pass
    return False


def resolve_post_login_mfa_redirect(request, user, *, next_url: str = ""):
    """
    Return an HttpResponseRedirect to MFA setup/verify, or None to continue.

    Call this AFTER ``login()`` and BEFORE any cross-host handoff so the MFA
    page is reached on the same host that just set the session cookie.
    """
    if not user or not getattr(user, "is_authenticated", False):
        return None
    if request.session.get("mfa_verified") or _mfa_remembered(request):
        return None

    try:
        from apps.accounts.e2e_mfa_bypass import e2e_mfa_bypass_active

        if e2e_mfa_bypass_active(request):
            request.session["mfa_verified"] = True
            return None
    except ImportError:
        pass

    has_device = _user_has_mfa_device(user)
    must_have = _user_must_have_mfa(request, user)

    if must_have and not has_device:
        mfa_setup_url = reverse("accounts:mfa_setup")
        # legacy=1 → branded enrollment page (wizard engine escape hatch).
        target = mfa_setup_url + "?legacy=1"
        if next_url:
            target = f"{target}&next={next_url}"
        request.session.modified = True
        return redirect(target)

    if has_device or must_have:
        if next_url:
            request.session["mfa_next"] = next_url
        request.session.modified = True
        return redirect(reverse("accounts:mfa_verify"))

    return None


def is_mfa_challenge_response(response) -> bool:
    """True when ``resolve_post_login_mfa_redirect`` produced a challenge redirect."""
    if not isinstance(response, HttpResponseRedirect):
        return False
    loc = (response.get("Location") or "").lower()
    return "/authentication/mfa/" in loc or "/mfa/" in loc
