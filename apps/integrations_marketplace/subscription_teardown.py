"""Tear down a connector's push subscription (and scrub its stored secrets)
when it is disconnected — the inverse of ``subscription_subscribe``.

``connector_connected`` auto-subscribes; without a matching teardown,
disconnecting a connector leaves the upstream push channel ALIVE:

* Google keeps POSTing change notifications to a now-dead webhook receiver,
* the Microsoft Graph subscription lingers until it expires, and
* the renewal worker keeps trying to rotate a subscription for a row the tenant
  already disconnected.

This receiver stops the upstream channel (Google ``channels/stop`` / Graph
``DELETE /subscriptions/{id}``), clears ``config["push_subscription"]`` so the
renewer skips it, and scrubs the stored OAuth secrets so a disconnected
integration does not retain live credentials at rest (a reconnect re-runs the
OAuth dance and mints fresh tokens).

Best-effort and self-isolating: an upstream stop failure still clears local
state (the channel expires on its own), and any crash is caught so the
disconnect flow is never blocked.
"""
from __future__ import annotations

import logging

from django.dispatch import receiver

from apps.integrations_marketplace.signals import connector_disconnected

logger = logging.getLogger(__name__)

_HTTP_TIMEOUT_SECONDS = 10  # magic-number-allow: outbound stop/delete timeout

# Mirror subscription_subscribe: which connectors created an upstream channel.
_GOOGLE_SLUG = "google_calendar"
_GRAPH_SLUGS = frozenset({"outlook_calendar", "outlook_mail", "microsoft_teams"})


def _http_json(method: str, url: str, token: str, body):
    """Outbound HTTP seam (patched in tests). Returns ``(status, parsed)``;
    ``status`` 0 = transport error (never raises)."""
    try:
        import requests

        resp = requests.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body if body is not None else None,
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        try:
            parsed = resp.json()
        except (ValueError, TypeError):
            parsed = {}
        return int(resp.status_code), parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001 — transport faults must not break teardown
        logger.warning("teardown HTTP %s %s failed", method, url, exc_info=True)
        return 0, {}


def _row_bearer(row) -> str:
    """Decrypt the row's own ``access_token``.

    ``get_valid_access_token`` filters ``is_active=True`` and a disconnect has
    just flipped the row inactive, so we decrypt the row's config directly (the
    token is still present until we scrub it below).
    """
    try:
        from apps.communication.secret_config import decrypt_config

        return str(
            (decrypt_config(dict(row.config or {})).get("access_token") or "")
        ).strip()
    except Exception:  # noqa: BLE001
        logger.warning("teardown could not decrypt token", exc_info=True)
        return ""


def _stop_google(token: str, sub: dict) -> dict:
    channel_id = sub.get("channel_id")
    resource_id = sub.get("resource_id")
    if not channel_id or not resource_id:
        return {"status": "no_channel"}
    status, _ = _http_json(
        "POST",
        "https://www.googleapis.com/calendar/v3/channels/stop",
        token,
        {"id": channel_id, "resourceId": resource_id},
    )
    return {
        "status": "stopped" if status in (200, 204) else "stop_failed",
        "http_status": status,
    }


def _delete_graph(token: str, sub: dict) -> dict:
    subscription_id = sub.get("subscription_id") or sub.get("channel_id")
    if not subscription_id:
        return {"status": "no_subscription_id"}
    status, _ = _http_json(
        "DELETE",
        f"https://graph.microsoft.com/v1.0/subscriptions/{subscription_id}",
        token,
        None,
    )
    # 404 = already gone upstream → idempotent success.
    return {
        "status": "stopped" if status in (200, 202, 204, 404) else "stop_failed",
        "http_status": status,
    }


def _scrub_secrets(config: dict) -> dict:
    """Return a copy of ``config`` without secret-named keys (access_token,
    refresh_token, client_secret, ...): a disconnected row keeps no live creds.
    """
    from apps.communication.secret_config import _is_secret_key

    return {k: v for k, v in config.items() if not _is_secret_key(k)}


def teardown_for_row(row, *, scrub_secrets: bool = True) -> dict:
    """Stop the upstream push subscription for ``row`` and clear local state.

    Idempotent: a row with no ``push_subscription`` just gets its secrets
    scrubbed. Always clears local subscription state even if the upstream stop
    failed (the channel expires on its own; leaving stale state would make the
    renewer try to rotate a dead subscription).
    """
    slug = (getattr(row, "connector_slug", "") or "").lower()
    config = dict(row.config or {})
    sub = config.get("push_subscription") or {}

    result = {"status": "no_subscription"}
    if isinstance(sub, dict) and sub.get("provider"):
        token = _row_bearer(row)
        if not token:
            result = {"status": "no_access_token"}
        elif slug == _GOOGLE_SLUG:
            result = _stop_google(token, sub)
        elif slug in _GRAPH_SLUGS:
            result = _delete_graph(token, sub)
        else:
            result = {"status": "no_teardown_for_slug"}

    changed = False
    if "push_subscription" in config:
        config.pop("push_subscription", None)
        changed = True
    if scrub_secrets:
        scrubbed = _scrub_secrets(config)
        if scrubbed != config:
            config = scrubbed
            changed = True
    if changed:
        row.config = config
        try:
            # update_fields keeps the disconnect's is_active=False write intact.
            row.save(update_fields=["config", "updated_at"])
        except Exception:  # noqa: BLE001
            logger.warning(
                "teardown could not persist config for row=%s",
                getattr(row, "pk", None),
                exc_info=True,
            )
    return {"row_id": getattr(row, "pk", None), "slug": slug, **result}


@receiver(
    connector_disconnected,
    dispatch_uid="im_teardown_on_disconnect",
    weak=False,
)
def _teardown_on_disconnect(sender, **kw):
    """Stop the upstream push subscription when a connector is disconnected."""
    row = kw.get("row")
    if row is None:
        return
    try:
        result = teardown_for_row(row)
        if result.get("status") == "stop_failed":
            logger.warning(
                "Push-subscription upstream stop failed for row=%s slug=%s status=%s",
                result.get("row_id"),
                result.get("slug"),
                result.get("http_status"),
            )
    except Exception:  # noqa: BLE001 — must not break the disconnect flow
        logger.exception(
            "Push-subscription teardown crashed for row=%s",
            getattr(row, "pk", None),
        )


__all__ = ["teardown_for_row"]
