"""
Canonical tenant lifecycle notification facade (NOTIF-001).

Routes to existing delivery modules without duplicating templates or event-bus
logic. Tracks dispatch status in ``School.settings["lifecycle_notifications"]``.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

logger = logging.getLogger(__name__)

SETTINGS_KEY = "lifecycle_notifications"

# Public event keys (stable contract for operators + tasks)
EVENT_PROVISIONING_STARTED = "provisioning_started"
EVENT_PROVISIONING_FAILED = "provisioning_failed"
EVENT_PROVISIONING_COMPLETED = "provisioning_completed"
EVENT_SETUP_READY = "setup_ready"
EVENT_SETUP_STALLED = "setup_stalled"
EVENT_LAUNCH_READY = "launch_ready"
EVENT_TENANT_ACTIVATED = "tenant_activated"

DELIVERY_QUEUED = "queued"
DELIVERY_SENT = "sent"
DELIVERY_SKIPPED = "skipped"
DELIVERY_DUPLICATE = "duplicate_suppressed"
DELIVERY_FAILED = "failed"
DELIVERY_BLOCKED = "blocked_email_backend"

_OPERATOR_ALERT_EVENTS = frozenset(
    {
        EVENT_PROVISIONING_FAILED,
        EVENT_SETUP_STALLED,
    }
)


def _notification_state(school) -> dict[str, Any]:
    settings_blob = dict(getattr(school, "settings", None) or {})
    state = settings_blob.get(SETTINGS_KEY) or {}
    return dict(state) if isinstance(state, dict) else {}


def _save_notification_state(school, state: dict[str, Any]) -> None:
    if not school or not getattr(school, "pk", None):
        return
    settings_blob = dict(getattr(school, "settings", None) or {})
    settings_blob[SETTINGS_KEY] = state
    school.settings = settings_blob
    try:
        school.save(update_fields=["settings", "updated_at"])
    except Exception:  # noqa: BLE001
        logger.warning("lifecycle_notification_state_save_failed", exc_info=True)


def _error_fingerprint(error: str) -> str:
    digest = hashlib.sha256((error or "unknown").encode("utf-8")).hexdigest()
    return digest[:12]


def should_suppress_duplicate(
    school,
    event: str,
    *,
    error: str = "",
    force: bool = False,
) -> bool:
    """True when this event was already dispatched for the same failure fingerprint."""
    if force or not school:
        return False
    state = _notification_state(school)
    dispatched_key = f"{event}_dispatched_at"
    if not state.get(dispatched_key):
        return False
    if event in _OPERATOR_ALERT_EVENTS and error:
        prior = (state.get(f"{event}_error_fingerprint") or "").strip()
        current = _error_fingerprint(error)
        if prior and prior != current:
            return False
    return True


def record_lifecycle_notification(
    school,
    event: str,
    *,
    status: str,
    error: str = "",
    channel: str = "",
) -> None:
    from django.utils import timezone

    state = _notification_state(school)
    now_iso = timezone.now().isoformat()
    state[f"{event}_dispatched_at"] = now_iso
    state[f"{event}_last_status"] = status
    if error:
        state[f"{event}_error_fingerprint"] = _error_fingerprint(error)
    if channel:
        state[f"{event}_last_channel"] = channel[:64]
    _save_notification_state(school, state)


def lifecycle_notification_history(school, *, limit: int = 12) -> list[dict[str, Any]]:
    """Operator-safe notification history from persisted lifecycle state."""
    if not school:
        return []
    state = _notification_state(school)
    rows: list[dict[str, Any]] = []
    for key, value in sorted(state.items()):
        if not key.endswith("_dispatched_at"):
            continue
        event = key[: -len("_dispatched_at")]
        rows.append(
            {
                "event": event,
                "dispatched_at": value,
                "status": state.get(f"{event}_last_status") or "",
            }
        )
    rows.sort(key=lambda r: r.get("dispatched_at") or "", reverse=True)
    return rows[:limit]


def emit_tenant_lifecycle_notification(
    school,
    event: str,
    *,
    contact_email: str = "",
    error: str = "",
    admin_user=None,
    force: bool = False,
) -> dict[str, Any]:
    """
    Idempotent lifecycle notification dispatch. Never raises to callers.
    """
    event = (event or "").strip()
    if not school:
        return {"ok": False, "status": DELIVERY_SKIPPED, "event": event, "reason": "no_school"}
    if not event:
        return {"ok": False, "status": DELIVERY_SKIPPED, "event": "", "reason": "no_event"}

    if should_suppress_duplicate(school, event, error=error, force=force):
        return {
            "ok": True,
            "status": DELIVERY_DUPLICATE,
            "event": event,
            "reason": "already_dispatched",
        }

    try:
        if event == EVENT_PROVISIONING_FAILED:
            from apps.schools.signup_completion_notifications import (
                notify_provisioning_failed_operator,
            )

            notify_provisioning_failed_operator(school, contact_email, error=error)
            record_lifecycle_notification(
                school, event, status=DELIVERY_QUEUED, error=error, channel="event_bus"
            )
            return {"ok": True, "status": DELIVERY_QUEUED, "event": event}

        if event in (EVENT_PROVISIONING_COMPLETED, EVENT_TENANT_ACTIVATED, EVENT_SETUP_READY):
            from apps.schools.signup_completion_notifications import (
                notify_tenant_signup_completed,
            )

            delivered = notify_tenant_signup_completed(
                school,
                contact_email,
                admin_user=admin_user,
                force=force,
            )
            status = DELIVERY_SENT if delivered else DELIVERY_QUEUED
            record_lifecycle_notification(school, event, status=status, channel="email")
            return {"ok": delivered, "status": status, "event": event}

        if event == EVENT_PROVISIONING_STARTED:
            record_lifecycle_notification(school, event, status=DELIVERY_QUEUED)
            return {"ok": True, "status": DELIVERY_QUEUED, "event": event}

        record_lifecycle_notification(school, event, status=DELIVERY_SKIPPED)
        return {"ok": False, "status": DELIVERY_SKIPPED, "event": event, "reason": "unhandled_event"}

    except ImportError as exc:
        record_lifecycle_notification(school, event, status=DELIVERY_BLOCKED, error=str(exc))
        return {
            "ok": False,
            "status": DELIVERY_BLOCKED,
            "event": event,
            "reason": "import_error",
        }
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "lifecycle_notification_emit_failed event=%s school=%s",
            event,
            getattr(school, "pk", None),
            exc_info=True,
        )
        record_lifecycle_notification(school, event, status=DELIVERY_FAILED, error=str(exc))
        return {"ok": False, "status": DELIVERY_FAILED, "event": event, "reason": str(exc)[:200]}
