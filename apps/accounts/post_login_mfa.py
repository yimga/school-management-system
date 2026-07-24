"""Post-password MFA routing — shared by login_view and handoff callers.

Keeps password → MFA → destination as one contract so manager/public handoff
cannot skip the MFA challenge (symptom: password “buffers” then returns to
the sign-in page, or lands on backend with MFA never shown).

Also respects soft-launch enforcement (optional/grace): brand-new owners must
not be hard-walled to verify/setup before they finish onboarding or when the
tenant policy only nudges.
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
    """Confirmed TOTP or passkey — the same surface RequireMFAMiddleware uses.

    A StaticDevice (backup codes) deliberately does NOT count: django_otp's
    ``user_has_device(confirmed=True)`` would include it, but a backup-codes-only
    user can't complete mfa_verify (it needs TOTP/passkey), so counting it would
    wall them in a verify<->setup bounce.
    """
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice

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


def _resolve_enforcement_mode(request, user):
    """Return (mode, grace_days) for resolve_mfa_enforcement."""
    from apps.accounts.mfa_defaults import principal_requires_strict_mfa

    if principal_requires_strict_mfa(
        user, getattr(request, "school", None)
    ):
        return "strict", None
    mode = None
    grace_days = None
    try:
        from apps.platform_runtime.config_resolver import get_effective_config

        mode = get_effective_config(
            key="mfa_enforcement_mode", request=request, default=None
        )
        grace_days = get_effective_config(
            key="mfa_grace_period_days", request=request, default=None
        )
    except (ImportError, AttributeError, TypeError, ValueError):
        pass
    if mode is None or str(mode).strip() == "":
        # Soft-launch façade default (see siteconfig.models_support virtual defaults).
        mode = "optional"
    return mode, grace_days


def _owner_onboarding_incomplete(request, user) -> bool:
    """True while the guided owner wizard is in progress (wizard owns MFA step)."""
    try:
        from apps.accounts.views_owner_onboarding import (
            _owner_school,
            onboarding_state,
        )

        school = getattr(request, "school", None) or _owner_school(user)
        if school is None:
            return False
        state = onboarding_state(school)
        if not state:
            return False
        return not bool(state.get("completed"))
    except Exception:  # noqa: BLE001 — login must never 500 on resume probe
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

    # A durable "trust this device" cookie means this browser already passed MFA
    # within the trust window. That is the cookie's PRIMARY stated purpose — "not
    # re-prompted on a re-login" — but only RequireMFAMiddleware honoured it, and
    # the middleware never sees this path: login redirects straight to
    # /mfa/verify/ (an exempt URL) before any gated page runs. So a device the
    # owner explicitly trusted during setup was still hard-prompted for a code on
    # its very next login. Honour it here too — re-establish the session flag and
    # continue — exactly as the middleware does (signed, user-bound, revoked by a
    # password change).
    try:
        from apps.accounts.mfa_device_trust import device_trust_valid

        if device_trust_valid(request, user):
            request.session["mfa_verified"] = True
            return None
    except (ImportError, AttributeError, TypeError, ValueError):
        pass

    try:
        from apps.accounts.e2e_mfa_bypass import e2e_mfa_bypass_active

        if e2e_mfa_bypass_active(request):
            request.session["mfa_verified"] = True
            return None
    except ImportError:
        pass

    has_device = _user_has_mfa_device(user)

    # Confirmed device → always challenge (even mid-onboarding). Skipping this
    # left enrolled owners on exempt onboarding URLs, then bouncing to login when
    # a later hop required MFA without a verified session.
    if has_device:
        if next_url:
            request.session["mfa_next"] = next_url
        request.session.modified = True
        return redirect(reverse("accounts:mfa_verify"))

    # Tenant policy is only relevant when the user still needs enrollment.
    # An enrolled user's challenge must not disappear because tenant config
    # resolution raises a soft database/config failure that login_view catches.
    must_have = _user_must_have_mfa(request, user)

    # Wizard owns enrollment when there is no confirmed device yet.
    if _owner_onboarding_incomplete(request, user):
        return None

    if not must_have:
        return None

    # Required role, no confirmed device — honor soft-launch modes.
    from apps.accounts.mfa_defaults import resolve_mfa_enforcement

    mode, grace_days = _resolve_enforcement_mode(request, user)
    decision = resolve_mfa_enforcement(
        must_have_mfa=True,
        has_device=False,
        mode=mode,
        grace_period_days=grace_days,
        user=user,
    )
    if decision.action in ("nudge", "grace", "none"):
        request.rmc_mfa_nudge = {
            "mode": decision.mode,
            "action": decision.action,
            "grace_days_remaining": decision.grace_days_remaining,
        }
        return None

    # strict / enforce → branded setup (never verify — there is no device yet).
    mfa_setup_url = reverse("accounts:mfa_setup")
    target = mfa_setup_url + "?legacy=1"
    if next_url:
        target = f"{target}&next={next_url}"
    request.session.modified = True
    return redirect(target)


def is_mfa_challenge_response(response) -> bool:
    """True when ``resolve_post_login_mfa_redirect`` produced a challenge redirect."""
    if not isinstance(response, HttpResponseRedirect):
        return False
    loc = (response.get("Location") or "").lower()
    return "/authentication/mfa/" in loc or "/mfa/" in loc
