"""
Phase 7 Task 2: MFA (Multi-Factor Authentication) views
Provides TOTP setup, QR code generation, and verification
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp import user_has_device, login as otp_login
from django.utils import timezone
from datetime import timedelta
from io import BytesIO
import qrcode
import base64
import secrets


def _get_or_create_backup_device(user):
    return StaticDevice.objects.get_or_create(user=user, name="backup")


def _generate_backup_tokens(device, count=10):
    device.token_set.all().delete()
    tokens = []
    for _ in range(count):
        token = f"{secrets.randbelow(10**8):08d}"
        StaticToken.objects.create(device=device, token=token)
        tokens.append(token)
    return tokens


@login_required
def mfa_setup(request):
    """
    Allow user to set up MFA (Time-based One-Time Password).
    Generates QR code for authenticator apps (Google Authenticator, Authy, etc.)
    """
    next_url = (request.POST.get("next") or request.GET.get("next") or "").strip()
    if next_url and (not next_url.startswith("/") or "//" in next_url):
        next_url = ""
    # Check if user already has MFA enabled
    has_mfa = user_has_device(request.user)
    
    backup_tokens = []
    if has_mfa:
        backup_device, _ = _get_or_create_backup_device(request.user)
        if backup_device.token_set.count() == 0:
            backup_tokens = _generate_backup_tokens(backup_device, count=10)
        else:
            backup_tokens = [t.token for t in backup_device.token_set.all()]

    if request.method == "POST":
        if "enable_mfa" in request.POST:
            # Generate new TOTP device
            device, created = TOTPDevice.objects.get_or_create(
                user=request.user,
                name="default"
            )
            device.confirmed = False
            device.save()
            
            # Generate QR code
            provisioning_uri = device.config_url
            qr = qrcode.QRCode(version=1, box_size=10, border=5)
            qr.add_data(provisioning_uri)
            qr.make(fit=True)
            
            img = qr.make_image(fill_color="black", back_color="white")
            buffer = BytesIO()
            img.save(buffer, format="PNG")
            img_str = base64.b64encode(buffer.getvalue()).decode()
            
            return render(request, "accounts/mfa_setup.html", {
                "has_mfa": has_mfa,
                "qr_code": img_str,
                "secret_key": device.key,
                "device_id": device.id,
                "backup_tokens": backup_tokens,
                "next_url": next_url,
            })
        
        elif "verify_token" in request.POST:
            token = request.POST.get("token", "").strip()
            device_id = request.POST.get("device_id")
            
            try:
                device = TOTPDevice.objects.get(id=device_id, user=request.user)
                if device.verify_token(token):
                    device.confirmed = True
                    device.save()
                    request.session["mfa_verified"] = True
                    messages.success(request, "MFA has been successfully enabled!")
                    if next_url:
                        return redirect(next_url)
                    return redirect("accounts:mfa_setup")
                else:
                    messages.error(request, "Invalid token. Please try again.")
            except TOTPDevice.DoesNotExist:
                messages.error(request, "Device not found.")
        
        elif "disable_mfa" in request.POST:
            # Delete all TOTP devices for user
            TOTPDevice.objects.filter(user=request.user).delete()
            StaticDevice.objects.filter(user=request.user).delete()
            messages.success(request, "MFA has been disabled.")
            return redirect("accounts:mfa_setup")
        elif "regen_backup" in request.POST:
            backup_device, _ = _get_or_create_backup_device(request.user)
            backup_tokens = _generate_backup_tokens(backup_device, count=10)
            messages.success(request, "Backup codes regenerated.")
    
    return render(request, "accounts/mfa_setup.html", {
        "has_mfa": has_mfa,
        "backup_tokens": backup_tokens,
        "next_url": next_url,
    })


@login_required
def dismiss_mfa_banner(request):
    """Dismiss the 'Set up MFA' encouragement banner for this session (e.g. from admin)."""
    request.session["mfa_banner_dismissed"] = True
    next_url = request.GET.get("next") or request.build_absolute_uri("/admin/")
    return redirect(next_url)


@login_required
def mfa_verify(request):
    """
    Verify MFA token during login.
    This view is called after successful password authentication.
    """
    if not user_has_device(request.user):
        # No MFA configured, proceed to dashboard
        return redirect("accounts:redirect")
    try:
        if not TOTPDevice.objects.filter(user=request.user, confirmed=True).exists():
            return redirect("accounts:mfa_setup")
    except Exception:
        pass

    # Capture next URL (GET) for post-verification redirect
    next_url = (request.POST.get("next") or request.GET.get("next") or request.session.get("mfa_next") or "").strip()
    if next_url and (not next_url.startswith("/") or "//" in next_url):
        next_url = ""
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
                except Exception:
                    pass
                request.session["mfa_verified"] = True
                remember = request.POST.get("remember_device") == "1"
                if remember:
                    until = timezone.now() + timedelta(days=14)
                    request.session["mfa_verified_until"] = until.isoformat()
                messages.success(request, "MFA verification successful!")
                request.session.pop("mfa_next", None)
                if next_url:
                    return redirect(next_url)
                return redirect("accounts:redirect")

        # Try backup codes
        backup_device = StaticDevice.objects.filter(user=request.user, name="backup").first()
        if backup_device:
            backup_token = backup_device.token_set.filter(token=token).first()
            if backup_token:
                backup_token.delete()
                try:
                    otp_login(request, backup_device)
                except Exception:
                    pass
                request.session["mfa_verified"] = True
                remember = request.POST.get("remember_device") == "1"
                if remember:
                    until = timezone.now() + timedelta(days=14)
                    request.session["mfa_verified_until"] = until.isoformat()
                messages.success(request, "Backup code accepted. MFA verified.")
                request.session.pop("mfa_next", None)
                if next_url:
                    return redirect(next_url)
                return redirect("accounts:redirect")
        
        messages.error(request, "Invalid MFA token. Please try again.")
    
    return render(request, "accounts/mfa_verify.html", {"next_url": next_url})


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
                until_dt = timezone.make_aware(until_dt, timezone.get_current_timezone())
            if timezone.now() <= until_dt:
                return True
        except Exception:
            pass
        req.session.pop("mfa_verified_until", None)
        return False

    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)
        
        if user_has_device(request.user):
            # User has MFA configured
            if not _session_has_valid_mfa(request):
                # MFA not verified in this session
                messages.warning(request, "Please verify your MFA token.")
                return redirect("accounts:mfa_verify")
        
        return view_func(request, *args, **kwargs)
    
    return wrapper
