"""
Emit domain events into the outbox. Call from service layer only (no model signals chaos).
Consumer processes outbox (see tasks.py) for webhooks, notifications, automation.
"""
from django.db import transaction


def emit_event(
    event_type: str,
    payload: dict,
    *,
    school_id=None,
    schema_name=None,
    idempotency_key=None,
    schema_version: str = "1.0",
):
    """
    Append a domain event to the outbox (same transaction as caller).
    Call from service layer after the business operation succeeds (26.2).
    """
    from apps.events.models import DomainEvent

    with transaction.atomic():
        DomainEvent.objects.create(
            event_type=event_type,
            payload=payload,
            school_id=school_id,
            schema_name=schema_name,
            idempotency_key=idempotency_key or None,
            schema_version=schema_version or "1.0",
        )
