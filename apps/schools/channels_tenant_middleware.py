"""
Channels ASGI middleware: bind WebSocket scope to host-resolved tenant.

Mirrors HTTP ``TenantMiddleware`` + membership guards so WS ingress cannot
cross tenants via session/JWT alone.
"""

from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth.models import AnonymousUser

logger = logging.getLogger(__name__)


def _host_from_scope(scope: dict[str, Any]) -> str:
    headers = dict(scope.get("headers") or [])
    forwarded = headers.get(b"x-forwarded-host", b"").decode("latin-1").strip()
    if forwarded:
        candidate = forwarded.split(",")[0].strip()
    else:
        candidate = headers.get(b"host", b"").decode("latin-1").strip()
    if ":" in candidate:
        candidate = candidate.split(":", 1)[0].strip()
    return candidate.lower()


def _fake_request_from_scope(scope: dict[str, Any], host: str) -> SimpleNamespace:
    headers = dict(scope.get("headers") or [])
    meta = {
        "HTTP_HOST": host,
        "HTTP_X_FORWARDED_HOST": headers.get(b"x-forwarded-host", b"").decode("latin-1"),
    }
    return SimpleNamespace(META=meta, path=scope.get("path", ""))


def _session_school_id(scope: dict[str, Any]) -> str | None:
    session = scope.get("session") or {}
    sid = (session.get("school_id") or session.get("active_school_id") or "").strip()
    return sid or None


def _jwt_school_id(scope: dict[str, Any]) -> str | None:
    cookies = scope.get("cookies") or {}
    token = cookies.get("rmc_rls_jwt") or ""
    if not token:
        return None
    try:
        from apps.tenancy.middleware_rls_jwt import _verify_jwt

        claims = _verify_jwt(token)
        if isinstance(claims, dict):
            raw = claims.get("school_id") or claims.get("tenant_id")
            return str(raw).strip() if raw else None
    except (ImportError, AttributeError, TypeError, ValueError):
        return None
    return None


def _bind_websocket_tenant_scope_sync(scope: dict[str, Any]) -> None:
    """Populate scope school fields; set school_access_denied when unsafe."""
    scope["school"] = None
    scope["school_id"] = None
    scope["school_access_denied"] = True
    scope["public_host_kind"] = ""

    user = scope.get("user")
    if user is None or isinstance(user, AnonymousUser) or not user.is_authenticated:
        return

    host = _host_from_scope(scope)
    if not host:
        return

    from apps.schools.host_routing import public_host_kind
    from apps.schools.middleware import _resolve_school_from_request
    from apps.schools.tenant_switch_security import user_may_access_school_api

    scope["public_host_kind"] = public_host_kind(host) or ""
    request = _fake_request_from_scope(scope, host)
    school = _resolve_school_from_request(request)
    if school is None:
        return

    session_school_id = _session_school_id(scope)
    jwt_school_id = _jwt_school_id(scope)

    if jwt_school_id and str(jwt_school_id) != str(school.pk):
        logger.warning("ws_tenant.jwt_host_mismatch host_school=%s jwt=%s", school.pk, jwt_school_id[:8])
        return
    if session_school_id and str(session_school_id) != str(school.pk):
        logger.warning("ws_tenant.session_host_mismatch host_school=%s session=%s", school.pk, session_school_id[:8])
        return

    if not user_may_access_school_api(
        user,
        school,
        session_school_id=session_school_id or jwt_school_id,
    ):
        return

    scope["school"] = school
    scope["school_id"] = str(school.pk)
    scope["school_access_denied"] = False


@sync_to_async(thread_sensitive=True)
def bind_websocket_tenant_scope(scope: dict[str, Any]) -> None:
    _bind_websocket_tenant_scope_sync(scope)


class TenantChannelsMiddleware:
    """Inner ASGI middleware — run inside AuthMiddlewareStack after user is known."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "websocket":
            await bind_websocket_tenant_scope(scope)
        return await self.inner(scope, receive, send)


def tenant_sync_room_name(prefix: str, scope: dict[str, Any]) -> str | None:
    """Build tenant-scoped channel group name or None when binding failed."""
    if scope.get("school_access_denied"):
        return None
    school_id = scope.get("school_id")
    user = scope.get("user")
    if not school_id or user is None or not getattr(user, "is_authenticated", False):
        return None
    return f"{prefix}_{school_id}_{user.pk}"
