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
    # Owner spec: the authenticator entry shows the product/tenant name
    # (RMC-<school>), NOT the raw username ("admin"/"nina"). The issuer already
    # carries RMC-<school>; use it as the account label too so the entry reads
    # "RMC-<school>" everywhere instead of leaking the username.
    label = issuer or str(device.user.get_username())
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


def apply_device_trust_on_enroll(request, response) -> None:
    """Make a just-completed MFA enrollment durable when the owner opted to trust
    this device.

    Confirming a TOTP is a proof-of-possession — the same proof the verify page
    accepts — so the freshly-enrolled owner should not be re-challenged for a code
    seconds later when the wizard hands them to their dashboard, nor on their next
    login from this same browser within the trust window. This mirrors the verify
    page's ``_mark_mfa_verified_and_redirect``: it sets the session markers and
    issues the signed, password-revocable device-trust cookie (which — see
    ``mfa_device_trust`` — is scoped to the session's own domain so it actually
    carries to the tenant subdomain).

    Scoped to the enroll-confirm action only (``verify_token`` in POST), so a
    ``disable_mfa`` / ``regen_backup`` POST never mints trust, and only when the
    owner left the box ticked (opt-out on a shared machine).
    """
    from datetime import timedelta

    from django.utils import timezone

    if "verify_token" not in request.POST:
        return
    if request.POST.get("remember_device") != "1":
        return
    from apps.accounts.mfa_device_trust import normalize_device_trust_days

    trust_days = normalize_device_trust_days(request.POST.get("trust_days"))
    request.session["mfa_verified"] = True
    request.session["mfa_verified_until"] = (
        timezone.now() + timedelta(days=trust_days)
    ).isoformat()
    try:
        from apps.accounts.mfa_device_trust import set_device_trust_cookie

        set_device_trust_cookie(
            response, request.user, request, trust_days=trust_days
        )
    except (AttributeError, TypeError, ValueError, OSError):
        # Trust cookie is best-effort; enrollment still succeeded.
        pass


def mfa_has_device(user) -> bool:
    """True when the user has a *confirmed* TOTP device or a passkey.

    Unconfirmed draft TOTP rows (created when the user clicks “show QR”) must
    NOT count — otherwise login/middleware send them to MFA *verify* before they
    have finished enrollment.

    A StaticDevice (backup codes) must NOT count either: django_otp's
    ``user_has_device(confirmed=True)`` would include it, but backup codes are a
    secondary factor — a user holding only backup codes can't complete
    mfa_verify (which needs TOTP/passkey), so treating them as "enrolled" bounces
    them between verify and setup. Check confirmed TOTP explicitly instead.
    """
    from apps.accounts.models import UserPasskey

    has_totp = TOTPDevice.objects.filter(user=user, confirmed=True).exists()
    return bool(has_totp or UserPasskey.objects.filter(user=user).exists())


def build_mfa_setup_context(request, *, next_url: str = "") -> dict:
    """Read-only MFA wizard state for templates."""
    from apps.accounts.mfa_device_trust import (
        device_trust_allowed_days,
        device_trust_default_days,
    )
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
        "mfa_trust_days_options": device_trust_allowed_days(),
        "mfa_trust_default_days": device_trust_default_days(),
    }


def _device_qr_context(request, device) -> dict:
    """QR image + secret + id for an (unconfirmed) TOTP device.

    Shared by the "show QR" step and the invalid-token re-render, so a mistyped
    code doesn't throw the QR/secret/device_id away and bounce the user back to
    the start screen.
    """
    provisioning_uri = build_totp_provisioning_uri(request, device)
    qr = qrcode.QRCode(version=1, box_size=10, border=5)
    qr.add_data(provisioning_uri)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = BytesIO()
    img.save(buffer, format="PNG")
    img_str = base64.b64encode(buffer.getvalue()).decode()
    return {"qr_code": img_str, "secret_key": device.key, "device_id": device.id}


def handle_mfa_setup_post(request, *, next_url: str = "") -> tuple[str, dict | None]:
    """
    Process MFA setup POST. Returns (outcome, context).
    outcome: redirect_profile | redirect_mfa_setup | render | none
    """
    user = request.user
    inline = request.POST.get("mfa_inline") == "1"

    if "enable_mfa" in request.POST:
        device, _created = TOTPDevice.objects.get_or_create(user=user, name="default")
        device.confirmed = False
        device.save()
        ctx = build_mfa_setup_context(request, next_url=next_url)
        ctx.update(_device_qr_context(request, device))
        return ("render", ctx)

    if "verify_token" in request.POST:
        token = request.POST.get("token", "").strip()
        device_id = request.POST.get("device_id")
        try:
            device = TOTPDevice.objects.get(id=device_id, user=user)
        except (TOTPDevice.DoesNotExist, ValueError, TypeError):
            # A non-numeric/absent device_id makes the ORM's int coercion raise
            # ValueError/TypeError — that must not 500; treat it as "not found".
            messages.error(request, _("Device not found."))
            return ("render", build_mfa_setup_context(request, next_url=next_url))
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
        # Wrong code — re-render WITH the same device's QR/secret/device_id so the
        # user retries in place instead of being bounced to the start screen.
        messages.error(request, _("Invalid token. Please try again."))
        ctx = build_mfa_setup_context(request, next_url=next_url)
        ctx.update(_device_qr_context(request, device))
        return ("render", ctx)

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
