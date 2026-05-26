"""Helpers for Django Client tests against manager.runmycampus.com."""

from django.conf import settings
from django.contrib.sessions.backends.db import SessionStore


def bind_manager_session(client) -> None:
    """Mirror force_login session onto MANAGER_SESSION_COOKIE_NAME for manager host."""
    client.session.save()
    session_key = client.session.session_key
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    client.cookies[cookie_name] = session_key
    # Default session cookie too — keeps test client stable when middleware or keepdb vary.
    client.cookies[settings.SESSION_COOKIE_NAME] = session_key


def mark_manager_mfa_verified(client) -> None:
    """Persist MFA verification on the manager session store (RequireMFAMiddleware)."""
    bind_manager_session(client)
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    manager_cookie = client.cookies.get(cookie_name)
    session_key = (
        manager_cookie.value
        if manager_cookie
        else client.session.session_key
    )
    store = SessionStore(session_key=session_key)
    store.load()
    store["mfa_verified"] = True
    store["security_posture_review_nagged"] = True
    store.save()
    client.cookies[cookie_name] = store.session_key
    client.cookies[settings.SESSION_COOKIE_NAME] = store.session_key
