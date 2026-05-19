"""
v3.4 — initial subscribe flow for push-notification-capable connectors.

The v3.1 renewal worker rotates push subscriptions before they expire — but
it only rotates subscriptions that ALREADY EXIST. Without this module the
OAuth dance completes, the renewer walks empty `config["push_subscription"]`
forever, and no notifications ever arrive.

Wired as a receiver of `signals.connector_connected` so a successful OAuth
upsert automatically subscribes (when the connector supports push). Failure
to subscribe is non-fatal — the row stays connected and the operator can
re-trigger via `python manage.py subscribe_push <row_id>`.

Subscribers:
  - google_calendar       → POST /calendar/v3/calendars/<cal>/events/watch
  - outlook_calendar      → POST /v1.0/me/events                (Graph)
  - outlook_mail          → POST /v1.0/me/mailFolders/Inbox/messages
  - microsoft_teams       → POST /v1.0/teams (chat resources require sites)

Connectors without a push primitive (slack, stripe, zoom, gmail, ...) are
no-ops here; they receive events via the existing webhook receiver path
configured in the upstream marketplace console, NOT via subscription.
"""

from __future__ import annotations

import datetime as _dt
import json
import logging
import secrets
import time
import urllib.error
import urllib.request
from typing import Any

from django.conf import settings
from django.dispatch import receiver
from django.urls import reverse

from apps.integrations_marketplace.signals import connector_connected

logger = logging.getLogger(__name__)

# Initial subscription windows (the renewer uses its own constants; these are
# the *creation* values upstream accepts).
GOOGLE_INITIAL_TTL_SECONDS = 30 * 24 * 60 * 60  # Google's max
GRAPH_INITIAL_TTL_SECONDS = 60 * 60 * 24 * 2     # 2 days, well under Graph caps


def _absolute_webhook_url(*, connector_slug: str, integration_id: int) -> str:
    """Build the absolute webhook receiver URL for this connector + row."""
    try:
        path = reverse(
            "integrations_marketplace:webhook_receiver",
            kwargs={"connector_slug": connector_slug,
                    "integration_id": integration_id},
        )
    except Exception:  # noqa: BLE001
        path = f"/integrations/webhook/{connector_slug}/{integration_id}/"
    base = str(getattr(settings, "OAUTH_CALLBACK_BASE_URL", "") or "").strip()
    if not base:
        # If the operator didn't set OAUTH_CALLBACK_BASE_URL the receiver
        # URL is unresolvable in a background task — defer.
        return ""
    return f"{base.rstrip('/')}{path}"


def _post_json(
    *, url: str, body: dict, access_token: str, method: str = "POST", timeout: int = 15
) -> tuple[int, dict[str, Any]]:
    encoded = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=encoded, method=method,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "Authorization": f"Bearer {access_token}",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            raw = resp.read().decode("utf-8", errors="replace")
            try:
                parsed = json.loads(raw) if raw else {}
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
        logger.warning("Subscribe transport error %s: %s", url, exc)
        return 0, {}


def _subscribe_google_calendar(*, row, webhook_url: str) -> dict[str, Any]:
    access_token = str((row.config or {}).get("access_token") or "").strip()
    if not access_token:
        return {"status": "unauthorized", "reason": "no_access_token"}
    calendar_id = (row.config or {}).get("calendar_id") or "primary"
    channel_id = f"rmc-{row.pk}-{int(time.time())}-{secrets.token_hex(4)}"
    body = {
        "id": channel_id,
        "type": "web_hook",
        "address": webhook_url,
        "params": {"ttl": str(GOOGLE_INITIAL_TTL_SECONDS)},
    }
    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        f"{calendar_id}/events/watch"
    )
    status, parsed = _post_json(url=url, body=body, access_token=access_token)
    if status == 0:
        return {"status": "transport_error"}
    if status == 401:
        return {"status": "unauthorized", "reason": "google_401"}
    if status >= 400:
        return {"status": "subscribe_failed", "http_status": status,
                "reason": str(parsed.get("error") or f"http_{status}")}
    return {
        "status": "subscribed",
        "subscription": {
            "provider": "google_calendar",
            "channel_id": parsed.get("id") or channel_id,
            "resource_id": parsed.get("resourceId") or "",
            "calendar_id": calendar_id,
            "address": webhook_url,
            "expires_at": time.time() + GOOGLE_INITIAL_TTL_SECONDS,
            "created_at": time.time(),
        },
    }


_GRAPH_RESOURCE_BY_SLUG = {
    "outlook_calendar": "/me/events",
    "outlook_mail": "/me/mailFolders('Inbox')/messages",
    "microsoft_teams": "/me/chats",
}


def _subscribe_graph(*, row, webhook_url: str, slug: str) -> dict[str, Any]:
    access_token = str((row.config or {}).get("access_token") or "").strip()
    if not access_token:
        return {"status": "unauthorized", "reason": "no_access_token"}
    resource = _GRAPH_RESOURCE_BY_SLUG.get(slug)
    if not resource:
        return {"status": "no_subscribe_resource_for_slug"}
    expiry_iso = (
        _dt.datetime.utcfromtimestamp(time.time() + GRAPH_INITIAL_TTL_SECONDS)
        .isoformat() + "Z"
    )
    body = {
        "changeType": "created,updated",
        "notificationUrl": webhook_url,
        "resource": resource,
        "expirationDateTime": expiry_iso,
        # clientState is included in every notification so the receiver can
        # cross-check (defense in depth on top of HMAC).
        "clientState": secrets.token_urlsafe(24),
    }
    status, parsed = _post_json(
        url="https://graph.microsoft.com/v1.0/subscriptions",
        body=body, access_token=access_token,
    )
    if status == 0:
        return {"status": "transport_error"}
    if status == 401:
        return {"status": "unauthorized", "reason": "graph_401"}
    if status >= 400:
        err = parsed.get("error")
        reason = (err.get("code") if isinstance(err, dict)
                  else str(err) if err else f"http_{status}")
        return {"status": "subscribe_failed", "http_status": status, "reason": str(reason)}
    return {
        "status": "subscribed",
        "subscription": {
            "provider": slug,
            "subscription_id": parsed.get("id") or "",
            "resource": resource,
            "client_state": body["clientState"],
            "expires_at": time.time() + GRAPH_INITIAL_TTL_SECONDS,
            "created_at": time.time(),
        },
    }


_SUBSCRIBERS = {
    "google_calendar": _subscribe_google_calendar,
    "outlook_calendar": lambda *, row, webhook_url:
        _subscribe_graph(row=row, webhook_url=webhook_url, slug="outlook_calendar"),
    "outlook_mail": lambda *, row, webhook_url:
        _subscribe_graph(row=row, webhook_url=webhook_url, slug="outlook_mail"),
    "microsoft_teams": lambda *, row, webhook_url:
        _subscribe_graph(row=row, webhook_url=webhook_url, slug="microsoft_teams"),
}


def subscribe_for_row(row) -> dict[str, Any]:
    """Public entry-point. Idempotent: if a subscription already exists,
    returns `{"status": "already_subscribed"}` without re-POSTing.
    """
    slug = (getattr(row, "connector_slug", "") or "").lower()
    subscriber = _SUBSCRIBERS.get(slug)
    if subscriber is None:
        return {"row_id": getattr(row, "pk", None), "slug": slug,
                "status": "no_subscribe_for_slug"}
    existing = (row.config or {}).get("push_subscription") or {}
    if isinstance(existing, dict) and existing.get("provider"):
        return {"row_id": row.pk, "slug": slug, "status": "already_subscribed"}
    webhook_url = _absolute_webhook_url(connector_slug=slug, integration_id=row.pk)
    if not webhook_url:
        return {"row_id": row.pk, "slug": slug, "status": "no_webhook_url",
                "reason": "OAUTH_CALLBACK_BASE_URL is not configured; can't build "
                          "the absolute webhook URL upstream needs."}
    result = subscriber(row=row, webhook_url=webhook_url)
    if result.get("status") == "subscribed":
        config = dict(row.config or {})
        config["push_subscription"] = result["subscription"]
        row.config = config
        row.save(update_fields=["config", "updated_at"])
    return {"row_id": row.pk, "slug": slug, **result}


@receiver(connector_connected, dispatch_uid="im_v34_auto_subscribe", weak=False)
def _auto_subscribe_on_connect(sender, **kw):
    """Best-effort: try to subscribe immediately after the OAuth upsert. If it
    fails (no access_token yet, transport hiccup), the operator can re-run
    via `python manage.py subscribe_push <row_id>`.
    """
    row = kw.get("row")
    if row is None:
        return
    slug = (kw.get("connector") or "").lower()
    if slug not in _SUBSCRIBERS:
        return
    try:
        result = subscribe_for_row(row)
        if result.get("status") not in {"subscribed", "already_subscribed"}:
            logger.warning(
                "Auto-subscribe did not complete for row=%s slug=%s status=%s reason=%s",
                row.pk, slug, result.get("status"), result.get("reason"),
            )
    except Exception:  # noqa: BLE001 — must not break the OAuth dance
        logger.exception("Auto-subscribe crashed for row=%s slug=%s", row.pk, slug)


__all__ = ["GOOGLE_INITIAL_TTL_SECONDS", "GRAPH_INITIAL_TTL_SECONDS",
           "subscribe_for_row"]
