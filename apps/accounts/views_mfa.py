"""
Phase 7 Task 2: MFA (Multi-Factor Authentication) views
Provides TOTP setup, QR code generation, and verification
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext as _
from django.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp import user_has_device, login as otp_login
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from datetime import timedelta

from apps.accounts.mfa_setup_flow import build_mfa_setup_context, handle_mfa_setup_post


def _mfa_template(request, name: str) -> str:
    if getattr(request, "public_host_kind", None) == "manager":
        stem, suffix = name.rsplit(".", 1)
        return f"{stem}_manager.{suffix}"
    return name


def _safe_next_url(request, candidate, fallback=""):
    if not candidate:
        return fallback
    value = str(candidate).strip()
    if not value:
        return fallback
    if url_has_allowed_host_and_scheme(
        url=value,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        return value
    return fallback


@login_required
def mfa_setup(request):
    """
    Allow user to set up MFA (Time-based One-Time Password).
    Generates QR code for authenticator apps (Google Authenticator, Authy, etc.)
    """
    next_url = _safe_next_url(
        request, request.POST.get("next") or request.GET.get("next"), ""
    )
    if request.method == "POST":
        outcome, ctx = handle_mfa_setup_post(request, next_url=next_url)
        if outcome == "redirect_profile":
            return redirect("accounts:user_profile")
        if outcome == "redirect_next" and next_url:
            return redirect(next_url)
        if outcome == "redirect_mfa_setup":
            return redirect("accounts:mfa_setup")
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
        return redirect("accounts:redirect")

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

        # Try to verify against all user's TOTP devices
        devices = TOTPDevice.objects.filter(user=request.user, confirmed=True)
        for device in devices:
            if device.verify_token(token):
                # Token verified successfully
                try:
                    otp_login(request, device)
                except (ValueError, TypeError, AttributeError, RuntimeError):
                    pass
                request.session["mfa_verified"] = True
                remember = request.POST.get("remember_device") == "1"
                if remember:
                    until = timezone.now() + timedelta(days=14)
                    request.session["mfa_verified_until"] = until.isoformat()
                messages.success(request, _("MFA verification successful!"))
                request.session.pop("mfa_next", None)
                if next_url:
                    return redirect(next_url)
                return redirect("accounts:redirect")

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
                request.session["mfa_verified"] = True
                remember = request.POST.get("remember_device") == "1"
                if remember:
                    until = timezone.now() + timedelta(days=14)
                    request.session["mfa_verified_until"] = until.isoformat()
                messages.success(request, _("Backup code accepted. MFA verified."))
                request.session.pop("mfa_next", None)
                if next_url:
                    return redirect(next_url)
                return redirect("accounts:redirect")

        messages.error(request, _("Invalid MFA token. Please try again."))

    from .views_passkey import _webauthn_available
    from .models import UserPasskey

    has_passkey = UserPasskey.objects.filter(user=request.user).exists()
    return render(
        request,
        _mfa_template(request, "accounts/mfa_verify.html"),
        {
            "next_url": next_url,
            "use_passkey": _webauthn_available() and has_passkey,
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

        has_mfa = (
            user_has_device(request.user)
            or UserPasskey.objects.filter(user=request.user).exists()
        )
        if has_mfa and not _session_has_valid_mfa(request):
            messages.warning(request, _("Please verify your MFA token."))
            return redirect("accounts:mfa_verify")
        return view_func(request, *args, **kwargs)

    return wrapper
