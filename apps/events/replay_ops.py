"""
Operator-safe replay helpers for :class:`~apps.events.models.DomainEvent` outbox rows.

Platform runtime replay stays on :func:`apps.platform_runtime.event_bus.replay_event`.
"""

from __future__ import annotations

import uuid
from typing import Any

from django.utils import timezone


def clone_domain_event_for_operator_replay(src: Any, *, actor: Any | None = None) -> Any:
    """
    Clone a processed/failed/pending DomainEvent into a new **pending** outbox row.

    Adds ``payload._replay_meta`` (actor, timestamp, source id) for audit — never mutates ``src``.
    """
    from apps.events.models import DomainEvent

    payload = dict(src.payload or {})
    replay_meta = {
        "source_event_id": str(src.id),
        "replayed_at": timezone.now().isoformat(),
        "actor_id": getattr(actor, "pk", None) if actor is not None else None,
        "source": "events.replay_ops.clone_domain_event_for_operator_replay",
    }
    payload["_replay_meta"] = replay_meta

    return DomainEvent.objects.create(
        event_type=src.event_type,
        payload=payload,
        school_id=src.school_id,
        schema_name=src.schema_name,
        schema_version=getattr(src, "schema_version", None) or "1.0",
        status=DomainEvent.Status.PENDING,
        idempotency_key=f"{src.id}-replay-{uuid.uuid4().hex}",
    )
