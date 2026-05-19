"""Helpers for Django Client tests against manager.runmycampus.com."""

from django.conf import settings


def bind_manager_session(client) -> None:
    """Mirror force_login session onto MANAGER_SESSION_COOKIE_NAME for manager host."""
    client.session.save()
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    client.cookies[cookie_name] = client.session.session_key
