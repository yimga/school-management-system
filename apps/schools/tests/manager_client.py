"""Helpers for Django Client tests against manager.runmycampus.com."""

from django.conf import settings


def bind_manager_session(client) -> None:
    """Mirror force_login session onto MANAGER_SESSION_COOKIE_NAME for manager host."""
    client.session.save()
    session_key = client.session.session_key
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    client.cookies[cookie_name] = session_key
    # Default session cookie too — keeps test client stable when middleware or keepdb vary.
    client.cookies[settings.SESSION_COOKIE_NAME] = session_key
