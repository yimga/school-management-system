"""Shared helpers for manager-host HTTP render smoke in verify_* scripts."""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import Client

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
    return user


def prepare_manager_smoke_client(client: Client) -> None:
    """Skip quarterly security-posture nag so layout probes reach 200 HTML."""
    session = client.session
    session[SESSION_NAG_KEY] = True
    session.save()
