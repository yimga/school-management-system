"""
Phase 7 Task 2: MFA (Multi-Factor Authentication) views
Provides TOTP setup, QR code generation, and verification
"""

from django.shortcuts import render, redirect
from django.urls import reverse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp import user_has_device, login as otp_login
from django.utils import timezone
from datetime import timedelta

from apps.accounts.mfa_setup_flow import (
    apply_device_trust_on_enroll,
    build_mfa_setup_context,
    handle_mfa_setup_post,
)
from services.post_delete_navigation import safe_next_url as _safe_next_url
from apps.accounts.e2e_mfa_bypass import e2e_mfa_bypass_active


def _mark_mfa_verified_and_redirect(
    request, next_url: str, *, success_message=None
):
    request.session["mfa_verified"] = True
    remember = request.POST.get("remember_device") == "1"
    if remember:
        from apps.accounts.mfa_device_trust import normalize_device_trust_days

        trust_days = normalize_device_trust_days(request.POST.get("trust_days"))
        until = timezone.now() + timedelta(days=trust_days)
        request.session["mfa_verified_until"] = until.isoformat()
    messages.success(
        request, success_message or _("MFA verification successful!")
    )
    request.session.pop("mfa_next", None)
    response = redirect(next_url) if next_url else redirect("accounts:redirect")
    if remember:
        # Durable "trust this device": a signed cookie that survives a session
        # reset (pin flush, re-login, expiry), so a trusted device isn't
        # re-prompted for MFA within the trust window. Bound to the user's
        # session-auth-hash, so a password change revokes it.
        try:
            from apps.accounts.mfa_device_trust import set_device_trust_cookie

            set_device_trust_cookie(
                response, request.user, request, trust_days=trust_days
            )
        except Exception:  # noqa: BLE001 — trust cookie is best-effort; MFA still succeeded
            pass
    return response


def _mfa_template(request, name: str) -> str:
    if getattr(request, "public_host_kind", None) == "manager":
        stem, suffix = name.rsplit(".", 1)
        return f"{stem}_manager.{suffix}"
    return name


@login_required
def mfa_setup(request):
    """
    Allow user to set up MFA (Time-based One-Time Password).
    Generates QR code for authenticator apps (Google Authenticator, Authy, etc.)

    v4.00.12: Route through the Unified Wizard Engine via legacy_view_bridge.
    The engine carries the canonical JSON definition (apps/setup_studio/wizards/mfa_setup.json)
    + multi-audience support. Operators can opt out per-user via ``?legacy=1`` or per-deploy
    via ``RMC_WIZARD_ENGINE_OVERRIDES = {"mfa_setup": False}``.
    """
    try:
        from apps.setup_studio.legacy_view_bridge import engine_redirect_response

        resp = engine_redirect_response(request, "mfa_setup")
        if resp is not None:
            return resp
    except Exception:  # noqa: BLE001 — engine bridge is best-effort; legacy path remains safe
        pass

    next_url = _safe_next_url(
        request, request.POST.get("next") or request.GET.get("next"), ""
    )
    if request.method == "POST":
        outcome, ctx = handle_mfa_setup_post(request, next_url=next_url)
        if outcome == "redirect_profile":
            resp = redirect("accounts:user_profile")
            apply_device_trust_on_enroll(request, resp)
            return resp
        if outcome == "redirect_next" and next_url:
            resp = redirect(next_url)
            apply_device_trust_on_enroll(request, resp)
            return resp
        if outcome == "redirect_mfa_setup":
            resp = redirect("accounts:mfa_setup")
            apply_device_trust_on_enroll(request, resp)
            return resp
        if outcome == "render" and ctx:
            return render(request, _mfa_template(request, "accounts/mfa_setup.html"), ctx)

    return render(
        request,
        _mfa_template(request, "accounts/mfa_setup.html"),
        build_mfa_setup_context(request, next_url=next_url),
    )


@login_required
def dismiss_mfa_banner(request):
    """Dismiss the 'Set up MFA' encouragement banner for this session (e.g. from admin)."""
    request.session["mfa_banner_dismissed"] = True
    next_url = _safe_next_url(request, request.GET.get("next"), "/admin/")
    return redirect(next_url)


@login_required
def mfa_verify(request):
    """
    Verify MFA token during login.
    This view is called after successful password authentication.
    Accepts TOTP, backup codes, or passkey (when use_passkey and passkeys exist).
    """
    from .models import UserPasskey

    has_totp = TOTPDevice.objects.filter(user=request.user, confirmed=True).exists()
    has_passkey = UserPasskey.objects.filter(user=request.user).exists()
    if not has_totp and not has_passkey:
        # Never show the code entry page without a confirmed device — that is the
        # "asked for MFA before I enrolled" trap (often after an unconfirmed draft).
        setup = reverse("accounts:mfa_setup") + "?legacy=1"
        next_q = _safe_next_url(
            request,
            request.GET.get("next") or request.session.get("mfa_next"),
            "",
        )
        if next_q:
            setup = f"{setup}&next={next_q}"
        return redirect(setup)

    # Capture next URL (GET) for post-verification redirect
    next_url = _safe_next_url(
        request,
        request.POST.get("next")
        or request.GET.get("next")
        or request.session.get("mfa_next"),
        "",
    )
    if next_url:
        request.session["mfa_next"] = next_url

    if request.method == "POST":
        token = request.POST.get("token", "").strip()

        if e2e_mfa_bypass_active(request) and len(token) == 6 and token.isdigit():
            return _mark_mfa_verified_and_redirect(request, next_url)

        # Try to verify against all user's TOTP devices
        devices = TOTPDevice.objects.filter(user=request.user, confirmed=True)
        for device in devices:
            if device.verify_token(token):
                # Token verified successfully
                try:
                    otp_login(request, device)
                except (ValueError, TypeError, AttributeError, RuntimeError):
                    pass
                return _mark_mfa_verified_and_redirect(request, next_url)

        # Try backup codes
        backup_device = StaticDevice.objects.filter(
            user=request.user, name="backup"
        ).first()
        if backup_device:
            backup_token = backup_device.token_set.filter(token=token).first()
            if backup_token:
                backup_token.delete()
                try:
                    otp_login(request, backup_device)
                except (ValueError, TypeError, AttributeError, RuntimeError):
                    pass
                return _mark_mfa_verified_and_redirect(
                    request,
                    next_url,
                    success_message=_("Backup code accepted. MFA verified."),
                )

        messages.error(request, _("Invalid MFA token. Please try again."))

    from .views_passkey import _webauthn_available
    from .models import UserPasskey

    has_passkey = UserPasskey.objects.filter(user=request.user).exists()
    from apps.accounts.mfa_device_trust import (
        device_trust_allowed_days,
        device_trust_default_days,
    )

    return render(
        request,
        _mfa_template(request, "accounts/mfa_verify.html"),
        {
            "next_url": next_url,
            "use_passkey": _webauthn_available() and has_passkey,
            "mfa_trust_days_options": device_trust_allowed_days(),
            "mfa_trust_default_days": device_trust_default_days(),
        },
    )


def mfa_required(view_func):
    """
    Decorator to require MFA verification for sensitive views.
    Usage: @mfa_required
    """

    def _session_has_valid_mfa(req):
        if req.session.get("mfa_verified"):
            return True
        until_raw = req.session.get("mfa_verified_until")
        if not until_raw:
            return False
        try:
            until_dt = timezone.datetime.fromisoformat(until_raw)
            if timezone.is_naive(until_dt):
                until_dt = timezone.make_aware(
                    until_dt, timezone.get_current_timezone()
                )
            if timezone.now() <= until_dt:
                return True
        except (ValueError, TypeError, AttributeError):
            pass
        req.session.pop("mfa_verified_until", None)
        return False

    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)

        from .models import UserPasskey

        try:
            has_totp = bool(user_has_device(request.user, confirmed=True))
        except TypeError:
            has_totp = TOTPDevice.objects.filter(
                user=request.user, confirmed=True
            ).exists()
        has_mfa = has_totp or UserPasskey.objects.filter(user=request.user).exists()
        if has_mfa and not _session_has_valid_mfa(request):
            messages.warning(request, _("Please verify your MFA token."))
            return redirect("accounts:mfa_verify")
        if not has_mfa:
            return redirect(reverse("accounts:mfa_setup") + "?legacy=1")
        return view_func(request, *args, **kwargs)

    return wrapper
