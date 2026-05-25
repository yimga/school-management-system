"""Shared helpers for manager-host HTTP render smoke in verify_* scripts."""

from __future__ import annotations

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone

from apps.accounts.middleware_security_posture import SESSION_NAG_KEY

MANAGER_HOST = "manager.runmycampus.com"


def ensure_manager_smoke_user(username: str, *, password: str = "verify-pass"):
    """Return a staff superuser suitable for /admin/ and /super/ layout smoke."""
    User = get_user_model()
    user, _ = User.objects.get_or_create(
        username=username,
        defaults={"is_staff": True, "is_superuser": True},
    )
    if not user.is_staff or not user.is_superuser:
        user.is_staff = True
        user.is_superuser = True
        user.save(update_fields=["is_staff", "is_superuser"])
    if not user.check_password(password):
        user.set_password(password)
        user.save(update_fields=["password"])
    try:
        from apps.platform_runtime.operator_identity import ensure_platform_operator_profile

        ensure_platform_operator_profile(user, tier="break_glass")
    except Exception:
        pass
    return user


def prepare_manager_smoke_client(client: Client) -> None:
    """Skip manager-only guardrails so layout probes reach the target 200 HTML."""
    session = client.session
    session[SESSION_NAG_KEY] = True
    session["mfa_verified"] = True
    session["mfa_verified_until"] = (timezone.now() + timedelta(hours=2)).isoformat()
    session.save()

    user_id = client.session.get("_auth_user_id")
    if not user_id:
        return
    try:
        user = get_user_model().objects.get(pk=user_id)
    except Exception:
        return
    try:
        from django_otp.plugins.otp_totp.models import TOTPDevice
    except Exception:
        return
    TOTPDevice.objects.get_or_create(
        user=user,
        name="manager-render-smoke",
        defaults={"confirmed": True},
    )
