"""
Global event bus: publish (outbox) + in-process subscribers.

Webhook and Celery delivery remain in :mod:`apps.events.webhooks` / ``tasks``;
``dispatch_internal_subscribers`` runs after each outbox row is queued so workflows
and internal services can react without HTTP.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)

_SUBSCRIBERS: dict[str, list[Callable[[Any], Any]]] = {}


def subscribe(event_type: str, handler: Callable[[Any], Any]) -> None:
    """
    Register a synchronous handler for ``event_type``.

    ``event_type`` may be a concrete name (e.g. ``student.created``) or ``"*"`` for all events.
    Handlers receive the persisted :class:`~apps.events.models.DomainEvent` instance.
    """
    key = str(event_type or "").strip() or "*"
    _SUBSCRIBERS.setdefault(key, []).append(handler)


def unsubscribe(event_type: str, handler: Callable[[Any], Any]) -> None:
    key = str(event_type or "").strip() or "*"
    lst = _SUBSCRIBERS.get(key)
    if not lst:
        return
    try:
        lst.remove(handler)
    except ValueError:
        return
    if not lst:
        del _SUBSCRIBERS[key]


def clear_subscribers_for_tests() -> None:
    _SUBSCRIBERS.clear()


def dispatch_internal_subscribers(domain_event: Any) -> int:
    """
    Invoke registered handlers for ``domain_event.event_type`` and global ``"*"`` handlers.

    Failures are logged; processing continues (subscriber isolation).
    """
    et = str(getattr(domain_event, "event_type", "") or "")
    handlers = list(_SUBSCRIBERS.get(et, []))
    handlers.extend(_SUBSCRIBERS.get("*", []))
    executed = 0
    for fn in handlers:
        try:
            fn(domain_event)
            executed += 1
        except Exception:
            logger.exception(
                "internal event subscriber failed event_type=%s handler=%s",
                et,
                getattr(fn, "__name__", repr(fn)),
            )
    return executed


def publish(
    event_type: str,
    payload: dict[str, Any],
    *,
    school_id=None,
    schema_name=None,
    idempotency_key=None,
    schema_version: str = "1.0",
):
    """
    Publish to the transactional outbox (same as :func:`apps.events.services.emit_event`).
    Returns the persisted :class:`~apps.events.models.DomainEvent`.
    """
    from apps.events.services import emit_event

    return emit_event(
        event_type,
        payload,
        school_id=school_id,
        schema_name=schema_name,
        idempotency_key=idempotency_key,
        schema_version=schema_version,
    )
