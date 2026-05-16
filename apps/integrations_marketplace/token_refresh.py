"""
OAuth access-token refresh worker.

Most OAuth providers issue short-lived access tokens (1h for Zoom / Google /
Microsoft) and long-lived refresh tokens. Without proactive refresh, every
connection silently breaks ~1 hour after the OAuth dance — the user reconnects,
the integration works again for an hour, repeat forever.

This module:
- Looks at every active `ServiceIntegration` with a `connector_slug` in the
  registry and a `refresh_token` in config
- For each row whose access token is about to expire (within REFRESH_WINDOW
  seconds — default 600s / 10 minutes) OR whose token has no `expires_at`
  recorded but is older than 50 minutes
- POSTs `grant_type=refresh_token` to the upstream `token_url` using the
  platform's env-stored client credentials
- Updates `config.access_token` / `config.refresh_token` (some upstreams rotate
  it) / `config.expires_at` (epoch seconds)

Run as:
- Management command:    `python manage.py refresh_oauth_tokens` (CLI / cron)
- Celery beat task:       `apps.integrations_marketplace.token_refresh.refresh_due_oauth_tokens`
                          (already exported as a Celery `@shared_task`)

Failure handling:
- Network failures and 4xx responses are logged but do not raise; the row's
  `config["last_refresh_error"]` and `config["last_refresh_attempt_at"]` are
  updated so the operator can see why a connection broke.
- A 400 `invalid_grant` (refresh token revoked / expired) flips `is_active=False`
  and stamps `config["disconnect_reason"]="invalid_grant"`. The hub UI shows
  this as "Reconnect required".
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from apps.integrations_marketplace.connector_registry import (
    AUTH_KIND_OAUTH2,
    Connector,
    get_connector,
    resolve_oauth_client_credentials,
)
from apps.siteconfig.models_platform_catalog import ServiceIntegration

logger = logging.getLogger(__name__)

REFRESH_WINDOW_SECONDS = 600         # refresh tokens that expire in <10 min
DEFAULT_LIFETIME_SECONDS = 3600      # assume 1h when upstream returns no expires_in
NO_EXPIRY_RECORDED_MAX_AGE = 50 * 60  # if config has no expires_at, refresh after 50 min


def _is_due(config: dict[str, Any], now: float | None = None) -> bool:
    """Decide whether a row needs an access-token refresh right now."""
    if not isinstance(config, dict):
        return False
    if not config.get("refresh_token"):
        return False
    now = now if now is not None else time.time()
    expires_at = config.get("expires_at")
    if isinstance(expires_at, (int, float)):
        return float(expires_at) - now <= REFRESH_WINDOW_SECONDS
    # No expires_at recorded — refresh once per ~50 minutes based on last attempt.
    last_attempt = config.get("last_refresh_attempt_at") or config.get("issued_at") or 0
    try:
        last_attempt = float(last_attempt)
    except (TypeError, ValueError):
        last_attempt = 0
    return (now - last_attempt) >= NO_EXPIRY_RECORDED_MAX_AGE


def _post_token_refresh(
    *, token_url: str, body: dict[str, Any], timeout: int = 15
) -> tuple[int, dict[str, Any]]:
    """POST refresh request; returns (http_status, parsed_json). Status 0 = transport error."""
    if not token_url:
        return 0, {}
    encoded = urlencode({k: v for k, v in body.items() if v is not None}).encode("utf-8")
    req = urllib.request.Request(
        token_url,
        data=encoded,
        method="POST",
        headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 — token URL from registry
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw)
            except (TypeError, ValueError):
                parsed = {}
            return int(resp.status), parsed if isinstance(parsed, dict) else {}
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read().decode("utf-8", errors="replace")
            parsed = json.loads(raw)
        except (OSError, TypeError, ValueError):
            parsed = {}
        return int(exc.code), parsed if isinstance(parsed, dict) else {}
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        logger.warning("Refresh transport error %s: %s", token_url, exc)
        return 0, {}


def refresh_single(row: ServiceIntegration) -> dict[str, Any]:
    """
    Refresh one ServiceIntegration row's access token. Returns a status dict
    suitable for logging / management-command output.
    """
    slug = row.connector_slug or ""
    connector: Connector | None = get_connector(slug)
    if connector is None or connector.auth_kind != AUTH_KIND_OAUTH2:
        return {"row_id": row.pk, "slug": slug, "status": "skipped_non_oauth"}

    config = dict(row.config or {})
    refresh_token = str(config.get("refresh_token") or "").strip()
    if not refresh_token:
        return {"row_id": row.pk, "slug": slug, "status": "skipped_no_refresh_token"}

    client_id, client_secret = resolve_oauth_client_credentials(slug)
    if not client_id or not client_secret:
        return {
            "row_id": row.pk,
            "slug": slug,
            "status": "skipped_missing_platform_credentials",
        }

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    http_status, parsed = _post_token_refresh(token_url=connector.token_url, body=body)
    now = time.time()
    config["last_refresh_attempt_at"] = now

    if http_status == 0:
        config["last_refresh_error"] = "transport_error"
        row.config = config
        row.save(update_fields=["config", "updated_at"])
        return {"row_id": row.pk, "slug": slug, "status": "transport_error"}

    if http_status >= 400:
        error_code = str(parsed.get("error") or f"http_{http_status}")
        config["last_refresh_error"] = error_code
        # invalid_grant = refresh token revoked / expired; mark connection broken.
        if error_code in {"invalid_grant", "invalid_token"}:
            config["disconnect_reason"] = error_code
            row.is_active = False
            row.config = config
            row.save(update_fields=["config", "is_active", "updated_at"])
            return {
                "row_id": row.pk,
                "slug": slug,
                "status": "deactivated_invalid_grant",
                "http_status": http_status,
            }
        row.config = config
        row.save(update_fields=["config", "updated_at"])
        return {
            "row_id": row.pk,
            "slug": slug,
            "status": "refresh_failed",
            "http_status": http_status,
            "error": error_code,
        }

    access_token = str(parsed.get("access_token") or "").strip()
    if not access_token:
        config["last_refresh_error"] = "no_access_token_in_response"
        row.config = config
        row.save(update_fields=["config", "updated_at"])
        return {"row_id": row.pk, "slug": slug, "status": "refresh_failed_no_token"}

    config["access_token"] = access_token
    # Some upstreams rotate the refresh token; honor it.
    new_refresh = str(parsed.get("refresh_token") or "").strip()
    if new_refresh:
        config["refresh_token"] = new_refresh
    lifetime = parsed.get("expires_in") or DEFAULT_LIFETIME_SECONDS
    try:
        lifetime = int(lifetime)
    except (TypeError, ValueError):
        lifetime = DEFAULT_LIFETIME_SECONDS
    config["expires_at"] = now + lifetime
    config["issued_at"] = now
    config.pop("last_refresh_error", None)
    config.pop("disconnect_reason", None)
    row.config = config
    row.is_active = True
    row.save(update_fields=["config", "is_active", "updated_at"])
    return {
        "row_id": row.pk,
        "slug": slug,
        "status": "refreshed",
        "expires_in": lifetime,
    }


def refresh_due_oauth_tokens(*, dry_run: bool = False) -> list[dict[str, Any]]:
    """
    Walk every active OAuth-backed ServiceIntegration row and refresh those
    whose access token is about to expire. Returns one status dict per row
    examined (for management-command output and Celery logs).

    Note: this is the function Celery beat / cron should call. The bare
    `@shared_task` decorator is applied at import time below if Celery is on
    the path; if not, the function is still importable and callable.
    """
    out: list[dict[str, Any]] = []
    # tenant-isolation-allow: sweeper walks every tenant's OAuth rows by design;
    # the per-call refresh writes back only to that row's school.
    qs = ServiceIntegration.objects.filter(is_active=True).exclude(connector_slug="")
    for row in qs.iterator():
        if not _is_due(row.config or {}):
            out.append({"row_id": row.pk, "slug": row.connector_slug, "status": "not_due"})
            continue
        if dry_run:
            out.append(
                {"row_id": row.pk, "slug": row.connector_slug, "status": "would_refresh"}
            )
            continue
        try:
            out.append(refresh_single(row))
        except Exception as exc:  # noqa: BLE001 — last-resort log + continue sweeper
            logger.exception(
                "Unexpected refresh error for row %s: %s", row.pk, exc
            )
            out.append(
                {
                    "row_id": row.pk,
                    "slug": row.connector_slug,
                    "status": "unhandled_exception",
                }
            )
    return out


# Celery wrapper — optional. Imports lazily so non-Celery contexts (mgmt
# commands, tests, sync scripts) still work.
try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.refresh_due_oauth_tokens")
    def refresh_due_oauth_tokens_task() -> list[dict[str, Any]]:
        return refresh_due_oauth_tokens()
except ImportError:  # pragma: no cover — celery is in production deps
    refresh_due_oauth_tokens_task = None


__all__ = [
    "DEFAULT_LIFETIME_SECONDS",
    "NO_EXPIRY_RECORDED_MAX_AGE",
    "REFRESH_WINDOW_SECONDS",
    "_is_due",
    "refresh_due_oauth_tokens",
    "refresh_single",
]
