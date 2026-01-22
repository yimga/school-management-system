"""
Phase 7 Task 2: MFA (Multi-Factor Authentication) views
Provides TOTP setup, QR code generation, and verification
"""
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.conf import settings
from django_otp.plugins.otp_totp.models import TOTPDevice
from django_otp import user_has_device
from io import BytesIO
import qrcode
import base64


@login_required
def mfa_setup(request):
    """
    Allow user to set up MFA (Time-based One-Time Password).
    Generates QR code for authenticator apps (Google Authenticator, Authy, etc.)
    """
    # Check if user already has MFA enabled
    has_mfa = user_has_device(request.user)
    
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
            })
        
        elif "verify_token" in request.POST:
            token = request.POST.get("token", "").strip()
            device_id = request.POST.get("device_id")
            
            try:
                device = TOTPDevice.objects.get(id=device_id, user=request.user)
                if device.verify_token(token):
                    device.confirmed = True
                    device.save()
                    messages.success(request, "MFA has been successfully enabled!")
                    return redirect("accounts:mfa_setup")
                else:
                    messages.error(request, "Invalid token. Please try again.")
            except TOTPDevice.DoesNotExist:
                messages.error(request, "Device not found.")
        
        elif "disable_mfa" in request.POST:
            # Delete all TOTP devices for user
            TOTPDevice.objects.filter(user=request.user).delete()
            messages.success(request, "MFA has been disabled.")
            return redirect("accounts:mfa_setup")
    
    return render(request, "accounts/mfa_setup.html", {
        "has_mfa": has_mfa,
    })


@login_required
def mfa_verify(request):
    """
    Verify MFA token during login.
    This view is called after successful password authentication.
    """
    if not user_has_device(request.user):
        # No MFA configured, proceed to dashboard
        return redirect("accounts:redirect")
    
    if request.method == "POST":
        token = request.POST.get("token", "").strip()
        
        # Try to verify against all user's TOTP devices
        devices = TOTPDevice.objects.filter(user=request.user, confirmed=True)
        for device in devices:
            if device.verify_token(token):
                # Token verified successfully
                request.session["mfa_verified"] = True
                messages.success(request, "MFA verification successful!")
                return redirect("accounts:redirect")
        
        messages.error(request, "Invalid MFA token. Please try again.")
    
    return render(request, "accounts/mfa_verify.html")


def mfa_required(view_func):
    """
    Decorator to require MFA verification for sensitive views.
    Usage: @mfa_required
    """
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect(settings.LOGIN_URL)
        
        if user_has_device(request.user):
            # User has MFA configured
            if not request.session.get("mfa_verified", False):
                # MFA not verified in this session
                messages.warning(request, "Please verify your MFA token.")
                return redirect("accounts:mfa_verify")
        
        return view_func(request, *args, **kwargs)
    
    return wrapper
