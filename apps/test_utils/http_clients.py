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
    """Return a manager-host client with a committed session (use with TransactionTestCase)."""
    client = Client(HTTP_HOST=host, raise_request_exception=False)
    if not client.login(username=user.username, password=password):
        raise AssertionError(f"manager login failed for {user.username!r}")
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
