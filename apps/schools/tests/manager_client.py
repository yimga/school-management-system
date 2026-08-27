"""Helpers for Django Client tests against manager.runmycampus.com."""

from importlib import import_module

from django.conf import settings
from django.contrib.auth import BACKEND_SESSION_KEY, HASH_SESSION_KEY, SESSION_KEY
from django.contrib.auth.backends import ModelBackend


def _session_store(session_key=None):
    """Build a store using the CONFIGURED session engine.

    This module used to import ``SessionStore`` from
    ``django.contrib.sessions.backends.db`` directly. ``SESSION_ENGINE`` here is
    ``cached_db``, so that hardcoded import wrote straight to the database row
    while every real request read through the CACHE -- which still held the
    pre-write copy. The write landed and the request never saw it.

    The symptom was nine manager-host operator tests asserting 200 and getting
    302 to ``/authentication/mfa/verify/``: the session in the database had
    ``mfa_verified`` and the session the middleware read did not. Nothing about
    the failure pointed at the session backend, which is why it survived as a
    "known-red MFA thing" -- it looked like a permissions or host-routing bug.

    Resolving the engine from settings is what Django's own test ``Client``
    does, so the helper and the request now agree by construction.
    """
    engine = import_module(settings.SESSION_ENGINE)
    return engine.SessionStore(session_key)


def _manager_session_store(client):
    """Resolve the session store used on manager.runmycampus.com requests."""
    cookie_name = getattr(settings, "MANAGER_SESSION_COOKIE_NAME", "rmc_manager_sessionid")
    manager_cookie = client.cookies.get(cookie_name)
    if manager_cookie and str(manager_cookie.value or "").strip():
        store = _session_store(manager_cookie.value)
        store.load()
        return store
    client.session.save()
    return client.session


def bind_manager_session(client) -> None:
    """Mirror auth session onto MANAGER_SESSION_COOKIE_NAME for manager host.

    Only MINTS a session when there is not one yet. ``client.session`` is a
    property that builds a fresh ``SessionStore`` on every access, so calling
    ``.save()`` on it unconditionally re-wrote the row from whatever snapshot
    that instance happened to hold -- and this function is called immediately
    AFTER ``mark_manager_mfa_verified`` writes ``mfa_verified`` through a
    different store instance. The write landed and was then reverted, so every
    manager-host test arrived at a gated page with an authenticated session and
    no ``mfa_verified``, and got bounced to ``/authentication/mfa/verify/``.
    That cost nine operator-UI tests, all of which read as a permissions or
    routing problem and were none.
    """
    session_key = client.session.session_key
    if not session_key:
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

