"""Shared HTTP test clients for manager and tenant hosts."""

from __future__ import annotations

from django.test import Client

MANAGER_HOST = "manager.runmycampus.com"

MANAGER_TEST_DEFAULTS = {
    "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
    "SESSION_PINNING_ENABLED": False,
    "ROOT_URLCONF": "config.manager_urls",
}

TENANT_TEST_DEFAULTS = {
    "MULTI_TENANT_BASE_DOMAIN": "runmycampus.com",
    "SESSION_PINNING_ENABLED": False,
}


def login_manager_client(
    user,
    *,
    password: str,
    host: str = MANAGER_HOST,
) -> Client:
    """Return a manager-host client with a committed, MFA-satisfied operator session.

    Operators carry a baseline strict-MFA role (SUPERADMIN/finance/auditor/…), so
    ``RequireMFAMiddleware`` gates every manager page behind two checks: a confirmed
    MFA device (else it bounces to ``/authentication/mfa/setup/``) and a per-session
    ``mfa_verified`` flag (else it bounces to ``/authentication/mfa/verify/``). Give
    the user a confirmed TOTP device for the first gate, and delegate to the canonical
    control-plane login helper — which binds the manager session store (the manager
    host reads ``MANAGER_SESSION_COOKIE_NAME``) and marks MFA verified — for the second.
    """
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from apps.schools.tests.manager_client import login_manager_control_plane

    TOTPDevice.objects.get_or_create(user=user, name="test-manager-mfa", confirmed=True)
    client = Client(HTTP_HOST=host, raise_request_exception=False)
    login_manager_control_plane(client, user, password=password, host=host)
    return client


def login_tenant_client(
    user,
    *,
    password: str,
    host: str,
    mfa_verified: bool = True,
) -> Client:
    client = Client(HTTP_HOST=host, raise_request_exception=False)
    if not client.login(username=user.username, password=password):
        raise AssertionError(f"tenant login failed for {user.username!r}")
    if mfa_verified:
        session = client.session
        session["mfa_verified"] = True
        session.save()
    return client


def login_tenant_admin_client(
    user,
    *,
    password: str,
    host: str,
    school,
    role: str = "ADMIN",
) -> Client:
    """Fully-armed tenant-host client for a baseline-MFA admin reaching an operator
    control-plane page rendered on the tenant shell.

    Two guards gate such a request. ``OperatorTenantConfinementMiddleware``
    (``apps/accounts/middleware.py``) redirects any user with control-plane access
    but no ``SchoolMembership`` to ``manager/super/`` — a membership flips
    ``user_has_control_plane_access`` to False so a normal tenant admin passes
    (superusers keep the break-glass bypass, so they skip the membership).
    ``RequireMFAMiddleware`` then walls the baseline-MFA ADMIN role without a
    confirmed TOTP device (enforce) or a verified session (re-verify). Give the
    user a confirmed device and mark the session verified.
    """
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from apps.schools.models import SchoolMembership

    if not getattr(user, "is_superuser", False):
        SchoolMembership.objects.get_or_create(
            user=user,
            school=school,
            defaults={"role": role, "is_primary": True},
        )
    TOTPDevice.objects.get_or_create(
        user=user, name="test-tenant-mfa", confirmed=True
    )
    client = Client(HTTP_HOST=host, raise_request_exception=False)
    if not client.login(username=user.username, password=password):
        raise AssertionError(f"tenant login failed for {user.username!r}")
    session = client.session
    session["mfa_verified"] = True
    session.save()
    return client
