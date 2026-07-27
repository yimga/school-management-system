"""
WebAuthn/Passkey support alongside TOTP for MFA (25.5, 29.1).
Registration: add a passkey to the user account.
Authentication: verify with passkey and set mfa_verified (alternative to TOTP).
"""

import base64
import json
import secrets

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import render, redirect
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie

from .models import UserPasskey


def _webauthn_available():
    try:
        import webauthn  # noqa: F401

        return True
    except ImportError:
        return False


def _rp_id(request):
    """Relying party ID (hostname)."""
    out = getattr(settings, "WEBAUTHN_RP_ID", None) or request.get_host().split(":")[0]
    if out == "testserver":
        out = "localhost"
    return out


def _origin(request):
    return f"{request.scheme}://{request.get_host()}"


def _challenge_bytes(challenge_str):
    if isinstance(challenge_str, bytes):
        return challenge_str
    return challenge_str.encode("utf-8")


@login_required
@require_GET
def passkey_registration_options(request):
    """Return WebAuthn registration options (JSON) for the client."""
    if not _webauthn_available():
        return JsonResponse({"error": "WebAuthn not available"}, status=501)
    try:
        from webauthn import generate_registration_options, options_to_json

        user = request.user
        challenge = secrets.token_urlsafe(32)
        request.session["webauthn_registration_challenge"] = challenge

        options = generate_registration_options(
            rp_id=_rp_id(request),
            rp_name=getattr(settings, "WEBAUTHN_RP_NAME", "RunMyCampus"),
            user_id=str(user.pk).encode("utf-8"),
            user_name=user.get_username(),
            user_display_name=(
                getattr(user, "get_full_name", lambda: "")().strip()
                or user.get_username()
            ),
            challenge=_challenge_bytes(challenge),
        )
        return JsonResponse(json.loads(options_to_json(options)))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, AttributeError) as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def passkey_registration_verify(request):
    """Verify WebAuthn registration response and store credential."""
    if not _webauthn_available():
        return JsonResponse({"error": "WebAuthn not available"}, status=501)
    try:
        from webauthn import verify_registration_response

        data = json.loads(request.body)
        challenge = request.session.pop("webauthn_registration_challenge", None)
        if not challenge:
            return JsonResponse({"error": "No registration challenge"}, status=400)

        verification = verify_registration_response(
            credential=data,
            expected_challenge=_challenge_bytes(challenge),
            expected_rp_id=_rp_id(request),
            expected_origin=_origin(request),
        )
        credential_id_b64 = (
            base64.urlsafe_b64encode(verification.credential_id)
            .decode("utf-8")
            .rstrip("=")
        )
        public_key_b64 = (
            base64.urlsafe_b64encode(verification.credential_public_key)
            .decode("utf-8")
            .rstrip("=")
        )
        UserPasskey.objects.create(
            user=request.user,
            name=data.get("deviceName", "Passkey"),
            credential_id=credential_id_b64,
            public_key=public_key_b64,
            sign_count=verification.sign_count,
        )
        return JsonResponse({"ok": True})
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, AttributeError) as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_GET
def passkey_authentication_options(request):
    """Return WebAuthn authentication options (JSON) for the client."""
    if not _webauthn_available():
        return JsonResponse({"error": "WebAuthn not available"}, status=501)
    try:
        from webauthn import generate_authentication_options, options_to_json
        from webauthn.helpers.structs import PublicKeyCredentialDescriptor

        challenge = secrets.token_urlsafe(32)
        request.session["webauthn_authentication_challenge"] = challenge

        allow_credentials = []
        for pk in UserPasskey.objects.filter(user=request.user):
            raw_id = base64.urlsafe_b64decode((pk.credential_id + "==").encode("utf-8"))
            allow_credentials.append(
                PublicKeyCredentialDescriptor(id=raw_id, type="public-key")
            )
        options = generate_authentication_options(
            rp_id=_rp_id(request),
            challenge=_challenge_bytes(challenge),
            allow_credentials=allow_credentials if allow_credentials else None,
        )
        return JsonResponse(json.loads(options_to_json(options)))
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, AttributeError) as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@require_POST
def passkey_authentication_verify(request):
    """Verify WebAuthn authentication response and set mfa_verified."""
    if not _webauthn_available():
        return JsonResponse({"error": "WebAuthn not available"}, status=501)
    try:
        from webauthn import verify_authentication_response

        data = json.loads(request.body)
        challenge = request.session.pop("webauthn_authentication_challenge", None)
        if not challenge:
            return JsonResponse({"error": "No authentication challenge"}, status=400)

        # Client sends id (credential id, base64url). We store credential_id in UserPasskey.
        passkey = UserPasskey.objects.filter(
            user=request.user, credential_id=data["id"]
        ).first()
        if not passkey:
            return JsonResponse({"error": "Unknown credential"}, status=400)

        public_key = base64.urlsafe_b64decode(
            (passkey.public_key + "==").encode("utf-8")
        )
        verification = verify_authentication_response(
            credential=data,
            expected_challenge=_challenge_bytes(challenge),
            expected_rp_id=_rp_id(request),
            expected_origin=_origin(request),
            credential_public_key=public_key,
            credential_current_sign_count=passkey.sign_count,
        )
        passkey.sign_count = verification.new_sign_count
        passkey.save(update_fields=["sign_count"])

        request.session["mfa_verified"] = True
        from datetime import timedelta
        from django.utils import timezone

        response = JsonResponse({"ok": True})
        from apps.accounts.mfa_device_trust import (
            device_trust_opt_in,
            normalize_device_trust_days,
        )

        # Trust-period selection arms trust on its own (parity with the TOTP path);
        # the JSON remember_device boolean is still honored for back-compat.
        remember = device_trust_opt_in(
            remember_flag=data.get("remember_device"),
            trust_days_value=data.get("trust_days"),
        )
        if remember:
            trust_days = normalize_device_trust_days(data.get("trust_days"))
            until = timezone.now() + timedelta(days=trust_days)
            request.session["mfa_verified_until"] = until.isoformat()
            # Issue the durable device-trust cookie too — parity with the TOTP
            # path (mfa_setup_flow.apply_device_trust_on_enroll / views_mfa). A
            # per-session marker alone drops on a session flush / re-login, the
            # exact case the cookie exists to survive.
            try:
                from apps.accounts.mfa_device_trust import set_device_trust_cookie

                set_device_trust_cookie(
                    response, request.user, request, trust_days=trust_days
                )
            except (AttributeError, TypeError, ValueError, OSError):
                pass
        return response
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, AttributeError) as e:
        return JsonResponse({"error": str(e)}, status=400)


@login_required
@ensure_csrf_cookie
def passkey_verify_page(request):
    """MFA verify page: use passkey (or redirect to TOTP verify)."""
    from django_otp.plugins.otp_totp.models import TOTPDevice

    has_totp = TOTPDevice.objects.filter(user=request.user, confirmed=True).exists()
    has_passkey = UserPasskey.objects.filter(user=request.user).exists()
    if not has_totp and not has_passkey:
        return redirect("accounts:mfa_setup")
    from apps.accounts.mfa_device_trust import (
        device_trust_allowed_days,
        device_trust_default_days,
    )

    return render(
        request,
        "accounts/mfa_verify.html",
        {
            "next_url": request.GET.get("next", ""),
            "use_passkey": _webauthn_available() and has_passkey,
            "mfa_trust_days_options": device_trust_allowed_days(),
            "mfa_trust_default_days": device_trust_default_days(),
        },
    )
