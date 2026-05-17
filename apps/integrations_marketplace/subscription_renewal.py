"""
v2.100 — calendar push-subscription renewal worker.

Background:
- Google Calendar push notifications expire after ~30 days
  (https://developers.google.com/calendar/api/guides/push#renewing-channels)
- Microsoft Graph subscriptions expire after 3-4230 minutes depending on
  resource type (calendar/messages: max ~4230min ≈ 3 days)
  (https://learn.microsoft.com/en-us/graph/webhooks#creating-a-subscription)

Without proactive renewal, every push subscription silently dies. The user
sees calendar events stop syncing and has no idea why.

Subscription state lives on `ServiceIntegration.config["push_subscription"]`:
  {
    "provider": "google_calendar" | "microsoft_graph_calendar",
    "channel_id": "<google channel id>" | "<graph subscription id>",
    "resource_id": "<google resource id>",                    # google only
    "calendar_id": "primary",                                  # google only
    "subscription_id": "<graph subscription id>",              # graph only
    "expires_at": <epoch seconds>,
    "renewed_at": <epoch seconds>,
    "last_renewal_error": "<reason>"                           # set on failure
  }

Run as:
  - Management command: `python manage.py renew_push_subscriptions`
  - Celery beat:        `integrations_marketplace.renew_due_subscriptions` (hourly)
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from apps.integrations_marketplace.connector_registry import get_connector
from apps.observability.tracing import (
    finish_transaction,
    set_tags,
    set_transaction_status,
    start_named_transaction,
)
from apps.siteconfig.models_platform_catalog import ServiceIntegration

logger = logging.getLogger(__name__)

# Renew when expiry is within this many seconds — gives us plenty of margin
# to retry on transport hiccups before the subscription actually dies.
RENEWAL_WINDOW_SECONDS = 24 * 60 * 60        # 1 day
GOOGLE_RENEWAL_TTL_SECONDS = 30 * 24 * 60 * 60  # 30 days, Google's max
GRAPH_RENEWAL_TTL_SECONDS = 60 * 60 * 24 * 2    # 2 days (well under Graph cap)

_ALERT_STATUSES = frozenset({
    "renewal_failed",
    "transport_error",
    "unauthorized",
})


def _is_due(sub: dict[str, Any], now: float | None = None) -> bool:
    """Decide whether a subscription needs renewal right now."""
    if not isinstance(sub, dict):
        return False
    if not sub.get("provider"):
        return False
    expires_at = sub.get("expires_at")
    if not isinstance(expires_at, (int, float)):
        return False
    n = now if now is not None else time.time()
    return float(expires_at) - n <= RENEWAL_WINDOW_SECONDS


def _post_json(
    *, url: str, body: dict, access_token: str, method: str = "POST", timeout: int = 15
) -> tuple[int, dict[str, Any]]:
    """Helper for renewal HTTP calls. (0, {}) on transport error."""
    if not url:
        return 0, {}
    encoded = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=encoded,
        method=method,
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
        logger.warning("Subscription renewal transport error %s: %s", url, exc)
        return 0, {}


def _renew_google_calendar(
    *, row: ServiceIntegration, sub: dict[str, Any], now: float
) -> dict[str, Any]:
    """Re-subscribe to a Google Calendar channel.

    Google's renewal model is "stop then watch again" — there's no PATCH.
    We POST a fresh `events.watch` against the same calendar, which mints a
    new channel_id + resource_id + expiration. We then issue a best-effort
    stop on the old channel so we don't double-deliver.
    """
    access_token = str((row.config or {}).get("access_token") or "").strip()
    if not access_token:
        return {"status": "unauthorized", "reason": "no_access_token"}
    calendar_id = sub.get("calendar_id") or "primary"
    new_channel_id = f"rmc-{row.pk}-{int(now)}"
    body = {
        "id": new_channel_id,
        "type": "web_hook",
        "address": sub.get("address") or "",
        "params": {"ttl": str(GOOGLE_RENEWAL_TTL_SECONDS)},
    }
    if not body["address"]:
        return {"status": "renewal_failed", "reason": "missing_address"}
    url = (
        "https://www.googleapis.com/calendar/v3/calendars/"
        f"{calendar_id}/events/watch"
    )
    http_status, parsed = _post_json(url=url, body=body, access_token=access_token)
    if http_status == 0:
        return {"status": "transport_error"}
    if http_status == 401:
        return {"status": "unauthorized", "reason": "google_401"}
    if http_status >= 400:
        return {"status": "renewal_failed", "http_status": http_status,
                "reason": str(parsed.get("error") or f"http_{http_status}")}
    # Best-effort stop of the old channel.
    old_channel = sub.get("channel_id")
    old_resource = sub.get("resource_id")
    if old_channel and old_resource:
        _post_json(
            url="https://www.googleapis.com/calendar/v3/channels/stop",
            body={"id": old_channel, "resourceId": old_resource},
            access_token=access_token,
        )
    return {
        "status": "renewed",
        "channel_id": parsed.get("id") or new_channel_id,
        "resource_id": parsed.get("resourceId") or "",
        "expires_at": now + GOOGLE_RENEWAL_TTL_SECONDS,
    }


def _renew_graph_subscription(
    *, row: ServiceIntegration, sub: dict[str, Any], now: float
) -> dict[str, Any]:
    """Renew a Microsoft Graph subscription via PATCH expirationDateTime."""
    import datetime as _dt

    access_token = str((row.config or {}).get("access_token") or "").strip()
    if not access_token:
        return {"status": "unauthorized", "reason": "no_access_token"}
    subscription_id = sub.get("subscription_id") or sub.get("channel_id")
    if not subscription_id:
        return {"status": "renewal_failed", "reason": "no_subscription_id"}
    new_expiry = _dt.datetime.utcfromtimestamp(now + GRAPH_RENEWAL_TTL_SECONDS)
    body = {"expirationDateTime": new_expiry.isoformat() + "Z"}
    url = f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}"
    http_status, parsed = _post_json(
        url=url, body=body, access_token=access_token, method="PATCH"
    )
    if http_status == 0:
        return {"status": "transport_error"}
    if http_status == 401:
        return {"status": "unauthorized", "reason": "graph_401"}
    if http_status >= 400:
        return {"status": "renewal_failed", "http_status": http_status,
                "reason": str(parsed.get("error", {}).get("code")
                              if isinstance(parsed.get("error"), dict)
                              else parsed.get("error") or f"http_{http_status}")}
    return {
        "status": "renewed",
        "subscription_id": subscription_id,
        "expires_at": now + GRAPH_RENEWAL_TTL_SECONDS,
    }


_RENEWERS = {
    "google_calendar": _renew_google_calendar,
    "microsoft_graph_calendar": _renew_graph_subscription,
    "outlook_calendar": _renew_graph_subscription,
    "outlook_mail": _renew_graph_subscription,
    "microsoft_teams": _renew_graph_subscription,
}


def renew_single(row: ServiceIntegration) -> dict[str, Any]:
    """Renew one row's push subscription. Returns a status dict."""
    config = dict(row.config or {})
    sub = config.get("push_subscription") or {}
    if not isinstance(sub, dict) or not sub:
        return {"row_id": row.pk, "slug": row.connector_slug, "status": "no_subscription"}
    provider = str(sub.get("provider") or row.connector_slug or "").strip().lower()
    renewer = _RENEWERS.get(provider)
    if renewer is None:
        return {"row_id": row.pk, "slug": row.connector_slug,
                "status": "no_renewer_for_provider", "provider": provider}
    now = time.time()
    result = renewer(row=row, sub=sub, now=now)
    sub = dict(sub)  # copy before mutation
    sub["renewed_at"] = now
    status = result.get("status")
    if status == "renewed":
        # Merge renewer-emitted fields back into the subscription record.
        for k in ("channel_id", "resource_id", "subscription_id", "expires_at"):
            if k in result:
                sub[k] = result[k]
        sub.pop("last_renewal_error", None)
    else:
        sub["last_renewal_error"] = result.get("reason") or status or "unknown"
    config["push_subscription"] = sub
    row.config = config
    row.save(update_fields=["config", "updated_at"])
    return {"row_id": row.pk, "slug": row.connector_slug, **result}


def renew_due_subscriptions(*, dry_run: bool = False) -> list[dict[str, Any]]:
    """Walk active connector rows; renew any push subscription within the
    1-day window. Observability mirrors the token refresh sweep.
    """
    txn = start_named_transaction(
        "integrations_marketplace.renew_due_subscriptions",
        op="task.hot_path",
        dry_run="1" if dry_run else "0",
    )
    out: list[dict[str, Any]] = []
    try:
        # Cross-tenant sweeper by design; per-call renewal writes only to that row's school.
        qs = ServiceIntegration.objects.filter(is_active=True).exclude(connector_slug="")  # tenant-isolation-allow: cross-tenant sweeper, per-row writes only to row.school
        for row in qs.iterator():
            sub = (row.config or {}).get("push_subscription") or {}
            if not _is_due(sub):
                out.append({"row_id": row.pk, "slug": row.connector_slug,
                            "status": "not_due"})
                continue
            if dry_run:
                out.append({"row_id": row.pk, "slug": row.connector_slug,
                            "status": "would_renew"})
                continue
            try:
                result = renew_single(row)
            except Exception as exc:  # noqa: BLE001 — sweeper continues
                logger.exception("Renewal error for row %s: %s", row.pk, exc)
                result = {"row_id": row.pk, "slug": row.connector_slug,
                          "status": "unhandled_exception"}
            out.append(result)
            status = str(result.get("status") or "")
            if status in _ALERT_STATUSES:
                logger.warning(
                    "Subscription renewal alert: connector=%s row_id=%s status=%s",
                    result.get("slug"), result.get("row_id"), status,
                )
    finally:
        counts: dict[str, int] = {}
        for item in out:
            s = str(item.get("status") or "unknown")
            counts[s] = counts.get(s, 0) + 1
        try:
            tag_payload = {f"renew.{k}": str(v) for k, v in counts.items()}
            tag_payload["renew.examined"] = str(len(out))
            set_tags(**tag_payload)
            if txn is not None:
                for k, v in tag_payload.items():
                    try:
                        txn.set_tag(k, v)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001 — telemetry never blocks
            pass
        if any(counts.get(s, 0) for s in _ALERT_STATUSES):
            set_transaction_status(txn, "internal_error")
        else:
            set_transaction_status(txn, "ok")
        finish_transaction(txn)
        logger.info("Renewed push subscriptions — examined=%d counts=%s",
                    len(out), counts)
    return out


# Celery wrapper — optional, mirrors the token-refresh pattern.
try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.renew_due_subscriptions")
    def renew_due_subscriptions_task() -> list[dict[str, Any]]:
        return renew_due_subscriptions()
except ImportError:  # pragma: no cover
    renew_due_subscriptions_task = None


__all__ = [
    "GOOGLE_RENEWAL_TTL_SECONDS",
    "GRAPH_RENEWAL_TTL_SECONDS",
    "RENEWAL_WINDOW_SECONDS",
    "_is_due",
    "renew_due_subscriptions",
    "renew_single",
]
