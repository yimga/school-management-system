"""OAuth2 token issuance helpers (RFC 6749 subset)."""

from __future__ import annotations

import json
import secrets
from datetime import timedelta
from typing import Any

from django.utils import timezone

from apps.apicenter.models import (
    DeveloperApplication,
    OAuthAuthorizationCode,
    OAuthTokenPair,
    _hash_secret,
)

ACCESS_TOKEN_LIFETIME = timedelta(hours=1)
REFRESH_TOKEN_LIFETIME = timedelta(days=30)
CODE_LIFETIME = timedelta(minutes=10)


def verify_client_credentials(client_id: str, client_secret: str) -> DeveloperApplication | None:
    app = (
        DeveloperApplication.objects.filter(client_id=client_id, is_active=True)
        .order_by("id")
        .first()
    )
    if app is None:
        return None
    if not secrets.compare_digest(
        app.client_secret_hash, _hash_secret(client_secret)
    ):
        return None
    return app


def issue_token_pair(
    application: DeveloperApplication,
    *,
    user=None,
    scope: str = "",
) -> dict[str, Any]:
    """Create DB row and return raw access_token, refresh_token, expires_in."""
    now = timezone.now()
    raw_access = "rmc_at_" + secrets.token_urlsafe(48)
    raw_refresh = "rmc_rt_" + secrets.token_urlsafe(48)
    pair = OAuthTokenPair.objects.create(
        application=application,
        user=user,
        access_token_hash=_hash_secret(raw_access),
        refresh_token_hash=_hash_secret(raw_refresh),
        access_expires_at=now + ACCESS_TOKEN_LIFETIME,
        scope=scope or " ".join(application.scopes or []) or "read",
    )
    return {
        "access_token": raw_access,
        "refresh_token": raw_refresh,
        "expires_in": int(ACCESS_TOKEN_LIFETIME.total_seconds()),
        "token_type": "Bearer",
        "scope": pair.scope,
    }


def revoke_token_pair(pair: OAuthTokenPair) -> None:
    now = timezone.now()
    pair.revoked_at = now
    pair.save(update_fields=["revoked_at"])


def exchange_refresh_token(
    raw_refresh: str, application: DeveloperApplication
) -> dict[str, Any] | None:
    h = _hash_secret(raw_refresh)
    pair = (
        OAuthTokenPair.objects.filter(
            refresh_token_hash=h,
            application=application,
            revoked_at__isnull=True,
        )
        .order_by("-id")
        .first()
    )
    if pair is None:
        return None
    revoke_token_pair(pair)
    user = pair.user
    scope = pair.scope or ""
    return issue_token_pair(application, user=user, scope=scope)


def create_authorization_code(
    *,
    application: DeveloperApplication,
    user,
    redirect_uri: str,
    scope: str,
) -> str:
    raw = "rmc_ac_" + secrets.token_urlsafe(32)
    OAuthAuthorizationCode.objects.create(
        application=application,
        user=user,
        code_hash=_hash_secret(raw),
        redirect_uri=redirect_uri,
        scope=scope,
        expires_at=timezone.now() + CODE_LIFETIME,
    )
    return raw


def consume_authorization_code(
    raw_code: str,
    *,
    application: DeveloperApplication,
    redirect_uri: str,
) -> tuple[Any, str] | None:
    """Return (user, scope) if valid; None otherwise."""
    h = _hash_secret(raw_code)
    now = timezone.now()
    row = (
        OAuthAuthorizationCode.objects.filter(
            code_hash=h,
            application=application,
            used_at__isnull=True,
            expires_at__gt=now,
        )
        .select_related("user")
        .order_by("-id")
        .first()
    )
    if row is None:
        return None
    if row.redirect_uri != redirect_uri:
        return None
    row.used_at = now
    row.save(update_fields=["used_at"])
    scope = row.scope or ""
    return row.user, scope


def parse_token_request_body(request) -> dict[str, str]:
    """Parse application/x-www-form-urlencoded or JSON body."""
    ct = (request.content_type or "").split(";")[0].strip().lower()
    if ct == "application/json" and request.body:
        try:
            data = json.loads(request.body.decode("utf-8") or "{}")
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items() if v is not None}
        return {}
    from urllib.parse import parse_qsl

    try:
        raw = request.body.decode("utf-8") if request.body else ""
    except UnicodeDecodeError:
        raw = ""
    out = {k: v for k, v in parse_qsl(raw, keep_blank_values=True)}
    # Some proxies/TestClient paths populate POST while raw-body replay differs.
    if request.POST:
        for key, value in request.POST.items():
            out.setdefault(str(key), str(value))
    return out
