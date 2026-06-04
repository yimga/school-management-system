"""Helpers for Django Client tests against manager.runmycampus.com."""

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.backends import ModelBackend
from django.contrib.sessions.backends.db import SessionStore


def _manager_session_store(client):
    """Resolve the session store used on manager.runmycampus.com requests."""
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    manager_cookie = client.cookies.get(cookie_name)
    if manager_cookie and str(manager_cookie.value or "").strip():
        store = SessionStore(session_key=manager_cookie.value)
        store.load()
        return store
    client.session.save()
    return client.session


def bind_manager_session(client) -> None:
    """Mirror auth session onto MANAGER_SESSION_COOKIE_NAME for manager host."""
    client.session.save()
    session_key = client.session.session_key
    if not session_key:
        manager_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
        mgr = client.cookies.get(manager_name)
        if mgr and str(mgr.value or "").strip():
            session_key = mgr.value
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    client.cookies[cookie_name] = session_key
    if session_key:
        client.cookies[settings.SESSION_COOKIE_NAME] = session_key


def mark_manager_mfa_verified(client) -> None:
    """Persist MFA verification on the manager session store (RequireMFAMiddleware)."""
    bind_manager_session(client)
    session = _manager_session_store(client)
    session["mfa_verified"] = True
    session["security_posture_review_nagged"] = True
    session.modified = True
    session.save()
    bind_manager_session(client)


def login_manager_control_plane(
    client,
    user,
    *,
    password: str,
    host: str = "manager.runmycampus.com",
) -> None:
    """
    Authenticate for manager.runmycampus.com /super/ HTTP tests.

    ``Client.login`` + ``force_login`` both write to ``client.session``; on the
    manager host ``ManagerCookieIsolationMiddleware`` reads the manager-named
    cookie. Persist auth on that store explicitly so middleware + view decorators
    see an authenticated operator.
    """
    client.get("/authentication/login/", HTTP_HOST=host)
    if not client.login(username=user.username, password=password):
        client.force_login(user, backend="django.contrib.auth.backends.ModelBackend")
    bind_manager_session(client)
    store = _manager_session_store(client)
    backend = getattr(user, "backend", None) or f"{ModelBackend.__module__}.{ModelBackend.__name__}"
    store[SESSION_KEY] = str(user.pk)
    store[BACKEND_SESSION_KEY] = backend
    if hasattr(user, "get_session_auth_hash"):
        store[HASH_SESSION_KEY] = user.get_session_auth_hash()
    store.modified = True
    store.save()
    bind_manager_session(client)
    mark_manager_mfa_verified(client)

