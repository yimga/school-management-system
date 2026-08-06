"""
v2.100 — mailbox fetch loop for OAuth-connected gmail / outlook_mail rows.

These connectors register and finish OAuth fine, but until this worker
existed, nothing actually READ inbound mail — they were scaffolding without
a runtime. The fetch loop:

  1. Walks every active ServiceIntegration where connector_slug is in
     {"gmail", "outlook_mail"} AND config has an access_token.
  2. Pulls *new* messages (since `config["mailbox_state"]["last_message_id"]`
     for gmail; since `config["mailbox_state"]["last_fetched_at"]` for graph)
     via the provider API.
  3. Fires `signals.mailbox_message_received` for each new message so
     per-tenant code can react.
  4. Updates `config["mailbox_state"]` cursor so the next run resumes
     incrementally.

Per-tenant business logic (auto-ticket-create from a parent email, parse
WhatsApp opt-in forms, etc.) plugs in via the signal — same pattern as
`webhook_received`.

Run as:
  - Management command: `python manage.py fetch_mailboxes`
  - Celery beat:        `integrations_marketplace.fetch_due_mailboxes` (every 5 min)
"""

from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from apps.integrations_marketplace.signals import mailbox_message_received
from apps.observability.tracing import (
    finish_transaction,
    set_tags,
    set_transaction_status,
    start_named_transaction,
)
from apps.siteconfig.models_platform_catalog import ServiceIntegration

logger = logging.getLogger(__name__)

# Don't drown a tenant with backfill on first run — cap per-row pull.
MAX_MESSAGES_PER_FETCH = 25
FETCH_TIMEOUT_SECONDS = 20

_ALERT_STATUSES = frozenset({"fetch_failed", "transport_error", "unauthorized"})


def _http_get_json(
    *, url: str, access_token: str, timeout: int = FETCH_TIMEOUT_SECONDS
) -> tuple[int, dict[str, Any]]:
    """GET helper. (0, {}) on transport error."""
    if not url:
        return 0, {}
    req = urllib.request.Request(
        url, method="GET",
        headers={
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
        logger.warning("Mailbox fetch transport error %s: %s", url, exc)
        return 0, {}


def _fetch_gmail(*, row: ServiceIntegration, state: dict) -> dict[str, Any]:
    """Pull unread messages from Gmail. Returns a result dict + emits signals."""
    access_token = str((row.config or {}).get("access_token") or "").strip()
    if not access_token:
        return {"status": "unauthorized", "reason": "no_access_token"}

    last_id = str(state.get("last_message_id") or "").strip()
    # We pull the message list (IDs only) then fetch each unseen one.
    params = {"q": "is:unread", "maxResults": str(MAX_MESSAGES_PER_FETCH)}
    list_url = (
        "https://gmail.googleapis.com/gmail/v1/users/me/messages?" + urlencode(params)
    )
    http_status, parsed = _http_get_json(url=list_url, access_token=access_token)
    if http_status == 0:
        return {"status": "transport_error"}
    if http_status == 401:
        return {"status": "unauthorized", "reason": "gmail_401"}
    if http_status >= 400:
        return {"status": "fetch_failed", "http_status": http_status,
                "reason": str(parsed.get("error", {}).get("message")
                              if isinstance(parsed.get("error"), dict)
                              else parsed.get("error") or f"http_{http_status}")}

    raw_messages = parsed.get("messages") or []
    if not isinstance(raw_messages, list):
        raw_messages = []
    # Stop when we hit the last-seen ID (resumable cursor).
    new_message_ids: list[str] = []
    for m in raw_messages:
        mid = str((m or {}).get("id") or "").strip()
        if not mid:
            continue
        if last_id and mid == last_id:
            break
        new_message_ids.append(mid)

    delivered = 0
    newest_id = last_id
    for mid in new_message_ids:
        msg_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{mid}?format=metadata"
        status, message = _http_get_json(url=msg_url, access_token=access_token)
        if status >= 400 or not isinstance(message, dict):
            continue
        if delivered == 0:
            newest_id = mid  # capture the newest first; older messages don't reorder
        try:
            mailbox_message_received.send_robust(
                sender="integrations_marketplace.mailbox",
                row=row, provider="gmail", message=message,
            )
        except Exception:  # noqa: BLE001
            logger.exception("mailbox_message_received dispatch crashed (gmail)")
        delivered += 1

    return {
        "status": "fetched",
        "delivered": delivered,
        "newest_message_id": newest_id,
    }


def _fetch_outlook_mail(*, row: ServiceIntegration, state: dict) -> dict[str, Any]:
    """Pull unread messages from the user's Outlook inbox via Graph."""
    access_token = str((row.config or {}).get("access_token") or "").strip()
    if not access_token:
        return {"status": "unauthorized", "reason": "no_access_token"}

    # Use a $top + $filter so we don't backfill the entire inbox; rely on
    # last_fetched_at as a soft cursor — Graph supports `receivedDateTime ge ...`.
    last_at = float(state.get("last_fetched_at") or 0) or (time.time() - 24 * 60 * 60)
    import datetime as _dt
    cursor = _dt.datetime.utcfromtimestamp(last_at).isoformat() + "Z"
    params = {
        "$top": str(MAX_MESSAGES_PER_FETCH),
        "$filter": f"isRead eq false and receivedDateTime ge {cursor}",
        "$orderby": "receivedDateTime desc",
        "$select": "id,subject,from,receivedDateTime",
    }
    url = "https://graph.microsoft.com/v1.0/me/mailFolders/Inbox/messages?" + urlencode(params)
    http_status, parsed = _http_get_json(url=url, access_token=access_token)
    if http_status == 0:
        return {"status": "transport_error"}
    if http_status == 401:
        return {"status": "unauthorized", "reason": "graph_401"}
    if http_status >= 400:
        err = parsed.get("error")
        reason = (err.get("code") if isinstance(err, dict)
                  else str(err) if err else f"http_{http_status}")
        return {"status": "fetch_failed", "http_status": http_status,
                "reason": str(reason)}

    messages = parsed.get("value") or []
    if not isinstance(messages, list):
        messages = []
    delivered = 0
    for message in messages:
        if not isinstance(message, dict):
            continue
        try:
            mailbox_message_received.send_robust(
                sender="integrations_marketplace.mailbox",
                row=row, provider="outlook_mail", message=message,
            )
        except Exception:  # noqa: BLE001
            logger.exception("mailbox_message_received dispatch crashed (outlook_mail)")
        delivered += 1

    return {"status": "fetched", "delivered": delivered}


_FETCHERS = {
    "gmail": _fetch_gmail,
    "outlook_mail": _fetch_outlook_mail,
}


def fetch_single(row: ServiceIntegration) -> dict[str, Any]:
    """Fetch one row's mailbox. Persists cursor + counts to config."""
    slug = (row.connector_slug or "").lower()
    fetcher = _FETCHERS.get(slug)
    if fetcher is None:
        return {"row_id": row.pk, "slug": slug, "status": "no_fetcher_for_slug"}
    config = dict(row.config or {})
    state = dict(config.get("mailbox_state") or {})
    result = fetcher(row=row, state=state)
    now = time.time()
    state["last_fetched_at"] = now
    if result.get("status") == "fetched":
        if result.get("newest_message_id"):
            state["last_message_id"] = result["newest_message_id"]
        state["last_delivered_count"] = int(result.get("delivered") or 0)
        state.pop("last_fetch_error", None)
    else:
        state["last_fetch_error"] = result.get("reason") or result.get("status") or "unknown"
    config["mailbox_state"] = state
    row.config = config
    row.save(update_fields=["config", "updated_at"])
    return {"row_id": row.pk, "slug": slug, **result}


def fetch_due_mailboxes(*, dry_run: bool = False) -> list[dict[str, Any]]:
    """Walk active gmail / outlook_mail rows and pull new messages."""
    txn = start_named_transaction(
        "integrations_marketplace.fetch_due_mailboxes",
        op="task.hot_path",
        dry_run="1" if dry_run else "0",
    )
    out: list[dict[str, Any]] = []
    try:
        # tenant-isolation-allow: sweeper walks all tenants by design.
        qs = ServiceIntegration.objects.filter(
            is_active=True, connector_slug__in=list(_FETCHERS.keys())
        )
        for row in qs.iterator():
            if dry_run:
                out.append({"row_id": row.pk, "slug": row.connector_slug,
                            "status": "would_fetch"})
                continue
            try:
                result = fetch_single(row)
            except Exception as exc:  # noqa: BLE001 — sweeper continues
                logger.exception("Mailbox fetch error for row %s: %s", row.pk, exc)
                result = {"row_id": row.pk, "slug": row.connector_slug,
                          "status": "unhandled_exception"}
            out.append(result)
            status = str(result.get("status") or "")
            if status in _ALERT_STATUSES:
                logger.warning(
                    "Mailbox fetch alert: row_id=%s slug=%s status=%s",
                    result.get("row_id"), result.get("slug"), status,
                )
    finally:
        counts: dict[str, int] = {}
        delivered_total = 0
        for item in out:
            s = str(item.get("status") or "unknown")
            counts[s] = counts.get(s, 0) + 1
            delivered_total += int(item.get("delivered") or 0)
        try:
            tag_payload = {f"fetch.{k}": str(v) for k, v in counts.items()}
            tag_payload["fetch.examined"] = str(len(out))
            tag_payload["fetch.delivered_total"] = str(delivered_total)
            set_tags(**tag_payload)
            if txn is not None:
                for k, v in tag_payload.items():
                    try:
                        txn.set_tag(k, v)
                    except Exception:  # noqa: BLE001
                        pass
        except Exception:  # noqa: BLE001
            pass
        if any(counts.get(s, 0) for s in _ALERT_STATUSES):
            set_transaction_status(txn, "internal_error")
        else:
            set_transaction_status(txn, "ok")
        finish_transaction(txn)
        logger.info("Fetched mailboxes — examined=%d delivered=%d counts=%s",
                    len(out), delivered_total, counts)
    return out


try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.fetch_due_mailboxes")
    def fetch_due_mailboxes_task() -> list[dict[str, Any]]:
        # SAFETY GATE: outbound mailbox polling per connected row. The beat drain
        # no-ops until an operator enables marketplace mailbox integrations.
        from django.conf import settings

        if not getattr(
            settings, "INTEGRATIONS_MARKETPLACE_OUTBOUND_SWEEPS_ENABLED", False
        ):
            return [{"status": "disabled_outbound_sweeps_gate_off"}]
        return fetch_due_mailboxes()
except ImportError:  # pragma: no cover
    fetch_due_mailboxes_task = None


__all__ = [
    "MAX_MESSAGES_PER_FETCH",
    "fetch_due_mailboxes",
    "fetch_single",
]
