"""Helpers for Django Client tests against manager.runmycampus.com."""

from django.conf import settings


def bind_manager_session(client) -> None:
    """Mirror force_login session onto MANAGER_SESSION_COOKIE_NAME for manager host."""
    client.session.save()
    session_key = client.session.session_key
    if not session_key:
        manager_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
        mgr = client.cookies.get(manager_name)
        if mgr and str(mgr.value or "").strip():
            session_key = mgr.value
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    client.cookies[cookie_name] = session_key
    # Default session cookie too — keeps test client stable when middleware or keepdb vary.
    if session_key:
        client.cookies[settings.SESSION_COOKIE_NAME] = session_key


def mark_manager_mfa_verified(client) -> None:
    """Persist MFA verification on the manager session store (RequireMFAMiddleware)."""
    bind_manager_session(client)
    session = client.session
    session["mfa_verified"] = True
    session["security_posture_review_nagged"] = True
    session.modified = True
    session.save()
    bind_manager_session(client)
