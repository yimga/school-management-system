"""Shared MFA setup context + POST handling for full page and inline profile wizard."""

from __future__ import annotations

from io import BytesIO
from base64 import b32encode
from urllib.parse import quote, urlencode
import base64
import secrets

import qrcode
from django.conf import settings
from django.contrib import messages
from django.utils.translation import gettext as _
from django_otp import user_has_device
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

# Product spec: the authenticator-app issuer is "RMC-<tenant_name>" so a user
# enrolled across multiple campuses can tell each 6-digit code apart.
_MFA_ISSUER_PREFIX = "RMC-"


def mfa_issuer_for_request(request) -> str:
    """Authenticator-app issuer label for this request's tenant.

    django_otp only supports a single global ``OTP_TOTP_ISSUER``; this resolves
    it per tenant to ``RMC-<school.name>``. Falls back to the platform issuer
    off-tenant (operator / manager host, where there is no ``request.school``).
    """
    school = getattr(request, "school", None)
    name = (getattr(school, "name", "") or "").strip()
    if name:
        # ':' is the issuer/label separator in the otpauth URI — strip it out.
        return f"{_MFA_ISSUER_PREFIX}{name}".replace(":", "")
    fallback = getattr(settings, "OTP_TOTP_ISSUER", "") or "RunMyCampus"
    return fallback.replace(":", "")


def build_totp_provisioning_uri(request, device) -> str:
    """Faithful reimplementation of django_otp's ``TOTPDevice.config_url`` with a
    per-tenant issuer (see :func:`mfa_issuer_for_request`)."""
    issuer = mfa_issuer_for_request(request)
    label = str(device.user.get_username())
    params = {
        "secret": b32encode(device.bin_key).decode("utf-8"),
        "algorithm": "SHA1",
        "digits": device.digits,
        "period": device.step,
    }
    urlencoded_params = urlencode(params)
    if issuer:
        label = f"{issuer}:{label}"
        urlencoded_params += "&issuer=" + quote(issuer)
    return f"otpauth://totp/{quote(label)}?{urlencoded_params}"


def _get_or_create_backup_device(user):
    return StaticDevice.objects.get_or_create(user=user, name="backup")


def _generate_backup_tokens(device, count=10):
    device.token_set.all().delete()
    tokens = []
    for _token_index in range(count):
        token = f"{secrets.randbelow(10**8):08d}"
        StaticToken.objects.create(device=device, token=token)
        tokens.append(token)
    return tokens


def mfa_has_device(user) -> bool:
    from apps.accounts.models import UserPasskey

    return bool(
        user_has_device(user)
        or UserPasskey.objects.filter(user=user).exists()
    )


def build_mfa_setup_context(request, *, next_url: str = "") -> dict:
    """Read-only MFA wizard state for templates."""
    from apps.accounts.views_passkey import _webauthn_available
    from apps.accounts.models import UserPasskey

    user = request.user
    has_mfa = mfa_has_device(user)
    backup_tokens = []
    if has_mfa:
        backup_device, _unused = _get_or_create_backup_device(user)
        if backup_device.token_set.count() == 0:
            backup_tokens = _generate_backup_tokens(backup_device, count=10)
        else:
            backup_tokens = [t.token for t in backup_device.token_set.all()]

    passkeys = list(
        UserPasskey.objects.filter(user=user).values("id", "name", "created_at")
    )
    for p in passkeys:
        if p.get("created_at"):
            p["created_at"] = p["created_at"].strftime("%Y-%m-%d")

    return {
        "has_mfa": has_mfa,
        "qr_code": None,
        "secret_key": None,
        "device_id": None,
        "backup_tokens": backup_tokens,
        "next_url": next_url,
        "use_passkey": _webauthn_available(),
        "passkeys": passkeys,
    }


def handle_mfa_setup_post(request, *, next_url: str = "") -> tuple[str, dict | None]:
    """
    Process MFA setup POST. Returns (outcome, context).
    outcome: redirect_profile | redirect_mfa_setup | render | none
    """
    from apps.accounts.views_passkey import _webauthn_available

    user = request.user
    inline = request.POST.get("mfa_inline") == "1"

    if "enable_mfa" in request.POST:
        device, _created = TOTPDevice.objects.get_or_create(user=user, name="default")
        device.confirmed = False
        device.save()
        provisioning_uri = build_totp_provisioning_uri(request, device)
        qr = qrcode.QRCode(version=1, box_size=10, border=5)
        qr.add_data(provisioning_uri)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white")
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        img_str = base64.b64encode(buffer.getvalue()).decode()
        ctx = build_mfa_setup_context(request, next_url=next_url)
        ctx.update(
            {
                "has_mfa": mfa_has_device(user),
                "qr_code": img_str,
                "secret_key": device.key,
                "device_id": device.id,
                "use_passkey": _webauthn_available(),
            }
        )
        return ("render", ctx)

    if "verify_token" in request.POST:
        token = request.POST.get("token", "").strip()
        device_id = request.POST.get("device_id")
        try:
            device = TOTPDevice.objects.get(id=device_id, user=user)
            if device.verify_token(token):
                device.confirmed = True
                device.save()
                request.session["mfa_verified"] = True
                messages.success(request, _("MFA has been successfully enabled!"))
                if inline:
                    return ("redirect_profile", None)
                if next_url:
                    return ("redirect_next", None)
                return ("redirect_mfa_setup", None)
            messages.error(request, _("Invalid token. Please try again."))
        except TOTPDevice.DoesNotExist:
            messages.error(request, _("Device not found."))
        return ("render", build_mfa_setup_context(request, next_url=next_url))

    if "disable_mfa" in request.POST:
        TOTPDevice.objects.filter(user=user).delete()
        StaticDevice.objects.filter(user=user).delete()
        messages.success(request, _("MFA has been disabled."))
        if inline:
            return ("redirect_profile", None)
        return ("redirect_mfa_setup", None)

    if "regen_backup" in request.POST:
        backup_device, _unused = _get_or_create_backup_device(user)
        _generate_backup_tokens(backup_device, count=10)
        messages.success(request, _("Backup codes regenerated."))
        return ("render", build_mfa_setup_context(request, next_url=next_url))

    return ("none", None)
