"""Push published ``school_events.SchoolEvent`` rows to a tenant's connected
Google Calendar / Outlook calendar.

The marketplace already stores calendar OAuth tokens (``google_calendar`` /
``outlook_calendar`` connectors) but nothing ever consumed them for event CRUD.
This module is the consumer:

* :func:`push_event_to_calendars` — create-or-update one event on every
  connected calendar provider for its school. Idempotent: the external event id
  and a content hash are stashed in ``SchoolEvent.metadata["calendar_sync"]`` so
  a re-run PATCHes an existing event (or skips it when unchanged) instead of
  duplicating it.
* :func:`sync_school_events` — sweep a school's upcoming published events and
  push any that are new or changed. Safe to call repeatedly (management command
  / beat).

Never raises into the caller: a not-connected provider is skipped, and a
transport / API failure is recorded in the result and left for the next sweep.
All outbound HTTP goes through the single :func:`_http_json` seam so tests patch
one symbol and never hit the network.
"""
from __future__ import annotations

import hashlib
import json
import logging
from datetime import timedelta
from datetime import timezone as dt_timezone
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)

#: Calendar connector slugs we push to (must exist in connector_registry).
CALENDAR_PROVIDERS = ("google_calendar", "outlook_calendar")

_HTTP_TIMEOUT_SECONDS = 10  # magic-number-allow: outbound calendar API timeout
_DEFAULT_EVENT_MINUTES = 60  # magic-number-allow: fallback duration when end_at is unset
_SWEEP_EVENT_CAP = 500  # magic-number-allow: max events pushed per school per sweep


def _http_json(method: str, url: str, token: str, body: dict[str, Any] | None):
    """POST/PATCH JSON with a bearer token. Returns ``(status_code, parsed)``.

    The single network seam — tests patch this. ``status_code`` 0 = transport
    error (never raises).
    """
    try:
        import requests

        resp = requests.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            json=body or {},
            timeout=_HTTP_TIMEOUT_SECONDS,
        )
        try:
            parsed = resp.json()
        except (ValueError, TypeError):
            parsed = {}
        return int(resp.status_code), parsed if isinstance(parsed, dict) else {}
    except Exception:  # noqa: BLE001 — transport faults must not break the sweep
        logger.warning("calendar_sync HTTP %s %s failed", method, url, exc_info=True)
        return 0, {}


def _event_window(event):
    """Return (start_utc, end_utc) as timezone-aware UTC datetimes."""
    start = event.start_at
    end = event.end_at or (start + timedelta(minutes=_DEFAULT_EVENT_MINUTES) if start else None)
    if start is not None and timezone.is_aware(start):
        start = start.astimezone(dt_timezone.utc)
    if end is not None and timezone.is_aware(end):
        end = end.astimezone(dt_timezone.utc)
    return start, end


def _event_content_hash(event) -> str:
    """Stable short hash of the fields we send, so we only re-push on change."""
    start, end = _event_window(event)
    payload = {
        "title": event.title or "",
        "description": (event.description or event.summary or ""),
        "location": _venue_name(event),
        "start": start.isoformat() if start else "",
        "end": end.isoformat() if end else "",
        "status": event.status,
    }
    blob = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()[:16]


def _venue_name(event) -> str:
    venue = getattr(event, "venue", None)
    if venue is not None:
        return str(getattr(venue, "name", "") or getattr(venue, "location", "") or "")
    return ""


def _push_google(token: str, event, external_id: str):
    """Create or update a Google Calendar event. Returns (external_id, ok)."""
    start, end = _event_window(event)
    if start is None:
        return external_id, False
    body = {
        "summary": event.title or "Event",
        "description": event.description or event.summary or "",
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": (end or start).isoformat(), "timeZone": "UTC"},
    }
    location = _venue_name(event)
    if location:
        body["location"] = location
    base = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
    if external_id:
        status, data = _http_json("PATCH", f"{base}/{external_id}", token, body)
    else:
        status, data = _http_json("POST", base, token, body)
    if status in (200, 201):
        return str(data.get("id") or external_id or ""), True
    logger.warning("calendar_sync google push failed: status=%s", status)
    return external_id, False


def _push_outlook(token: str, event, external_id: str):
    """Create or update a Microsoft Graph calendar event. Returns (external_id, ok)."""
    start, end = _event_window(event)
    if start is None:
        return external_id, False
    body = {
        "subject": event.title or "Event",
        "body": {"contentType": "text", "content": event.description or event.summary or ""},
        "start": {"dateTime": start.isoformat(), "timeZone": "UTC"},
        "end": {"dateTime": (end or start).isoformat(), "timeZone": "UTC"},
    }
    location = _venue_name(event)
    if location:
        body["location"] = {"displayName": location}
    base = "https://graph.microsoft.com/v1.0/me/events"
    if external_id:
        status, data = _http_json("PATCH", f"{base}/{external_id}", token, body)
    else:
        status, data = _http_json("POST", base, token, body)
    if status in (200, 201):
        return str(data.get("id") or external_id or ""), True
    logger.warning("calendar_sync outlook push failed: status=%s", status)
    return external_id, False


_PUSHERS = {
    "google_calendar": _push_google,
    "outlook_calendar": _push_outlook,
}


def push_event_to_calendars(event, *, providers=None) -> dict[str, Any]:
    """Create-or-update ``event`` on every connected calendar provider for its
    school. Idempotent via ``metadata["calendar_sync"]``. Returns a per-provider
    result dict; never raises.
    """
    school = getattr(event, "school", None)
    if school is None:
        return {"ok": False, "error": "event has no school"}

    from apps.integrations_marketplace.token_access import get_valid_access_token

    sync_state = dict((event.metadata or {}).get("calendar_sync") or {})
    content_hash = _event_content_hash(event)
    results: dict[str, Any] = {}
    changed = False
    now_iso = timezone.now().isoformat()

    for slug in (providers or CALENDAR_PROVIDERS):
        pusher = _PUSHERS.get(slug)
        if pusher is None:
            continue
        token = get_valid_access_token(school, slug)
        if not token:
            results[slug] = {"status": "not_connected"}
            continue
        prior = dict(sync_state.get(slug) or {})
        external_id = str(prior.get("external_id") or "")
        if external_id and prior.get("hash") == content_hash:
            results[slug] = {"status": "unchanged", "external_id": external_id}
            continue
        new_id, ok = pusher(token, event, external_id)
        if ok and new_id:
            sync_state[slug] = {
                "external_id": new_id,
                "hash": content_hash,
                "synced_at": now_iso,
            }
            results[slug] = {
                "status": "updated" if external_id else "created",
                "external_id": new_id,
            }
            changed = True
        else:
            results[slug] = {"status": "error"}

    if changed:
        md = dict(event.metadata or {})
        md["calendar_sync"] = sync_state
        event.metadata = md
        event.save(update_fields=["metadata", "updated_at"])
    return {"ok": True, "providers": results}


def sync_school_events(school=None, *, limit: int = _SWEEP_EVENT_CAP) -> dict[str, Any]:
    """Push upcoming PUBLISHED events that are new or changed since last sync.

    ``school`` scopes the sweep to one tenant; ``None`` sweeps every event
    visible in the current DB/schema (the caller supplies tenant context).
    """
    from apps.school_events.models import SchoolEvent

    # tenant-isolation-allow: calendar-sweep-runs-inside-run-with-tenant-context-so-events-are-schema-scoped
    qs = SchoolEvent.objects.filter(
        status=SchoolEvent.Status.PUBLISHED,
        start_at__gte=timezone.now(),
    ).select_related("school", "venue")
    if school is not None:
        qs = qs.filter(school=school)
    qs = qs.order_by("start_at")[:limit]

    pushed = 0
    skipped = 0
    errors = 0
    for event in qs:
        result = push_event_to_calendars(event)
        provider_results = (result.get("providers") or {}).values()
        if any(r.get("status") in ("created", "updated") for r in provider_results):
            pushed += 1
        elif any(r.get("status") == "error" for r in provider_results):
            errors += 1
        else:
            skipped += 1
    summary = {"pushed": pushed, "skipped": skipped, "errors": errors}
    logger.info("calendar_sync sweep summary=%s", summary)
    return summary


def _sync_calendar_events_all_tenants() -> dict[str, Any]:
    """Run :func:`sync_school_events` for every active school inside its own
    tenant context (schema in django-tenants, RLS otherwise). Used by the beat
    task; safe to call directly (management command). One tenant's failure is
    logged and skipped so it never stops the sweep.
    """
    from apps.schools.celery_tasks import _run_with_tenant_context
    from apps.schools.models import School

    totals = {"pushed": 0, "skipped": 0, "errors": 0, "schools_processed": 0}
    # tenant-isolation-allow: platform beat iterates active schools; each sweep runs
    # inside _run_with_tenant_context so SchoolEvent queries are tenant-scoped.
    for sid in School.objects.filter(is_active=True).values_list("id", flat=True):
        try:
            result = _run_with_tenant_context(
                school_id=sid,
                runnable=sync_school_events,
            )
        except Exception:  # noqa: BLE001 — never let one tenant abort the sweep
            logger.warning(
                "calendar_sync sweep failed for school=%s", sid, exc_info=True
            )
            continue
        totals["pushed"] += int((result or {}).get("pushed", 0))
        totals["skipped"] += int((result or {}).get("skipped", 0))
        totals["errors"] += int((result or {}).get("errors", 0))
        totals["schools_processed"] += 1
    logger.info("calendar_sync all-tenants sweep totals=%s", totals)
    return totals


# ---------------------------------------------------------------------------
# Celery wrapper (registered lazily when celery is importable). The AppConfig
# imports this module in ready() so the @shared_task registers before the beat
# scheduler reads the registry (bare autodiscover only imports <app>/tasks.py).
# ---------------------------------------------------------------------------
try:
    from celery import shared_task  # type: ignore

    @shared_task(name="integrations_marketplace.sync_calendar_events")
    def sync_calendar_events() -> dict[str, Any]:
        """Beat entry — push published upcoming events to each active tenant's
        connected calendars. Returns an audit dict (visible in the result
        backend)."""
        return _sync_calendar_events_all_tenants()
except Exception:  # pragma: no cover — celery not installed in some environments
    sync_calendar_events = None  # type: ignore[assignment]


__all__ = [
    "CALENDAR_PROVIDERS",
    "push_event_to_calendars",
    "sync_school_events",
    "sync_calendar_events",
]
