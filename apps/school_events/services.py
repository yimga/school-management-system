from decimal import Decimal

from django.db import models, transaction
from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.school_events.models import EventRegistration, EventTicketTier, SchoolEvent


class TicketCapacityError(Exception):
    """Raised when a registration would exceed tier remaining capacity."""


def upcoming_public_events_for_school(school, *, limit: int = 15) -> list[dict]:
    if school is None:
        return []
    events = (
        SchoolEvent.objects.filter(
            school=school,
            status=SchoolEvent.Status.PUBLISHED,
            is_public=True,
            start_at__gte=timezone.now(),
        )
        .select_related("venue")
        .order_by("start_at")[:limit]
    )
    return [
        {
            "title": event.title,
            "when": event.start_at,
            "detail": (
                event.summary
                or (event.venue.name if event.venue_id else "")
                or event.organizer_name
                or ""
            ).strip()
            or None,
            "kind": "event",
            "slug": event.slug,
        }
        for event in events
    ]


def event_operations_snapshot(school) -> dict:
    if school is None:
        return {
            "events_total": 0,
            "published_events": 0,
            "open_registrations": 0,
            "sponsor_commitments": 0,
            "sponsorship_total": 0,
        }
    totals = SchoolEvent.objects.filter(school=school).aggregate(
        events_total=Count("id"),
        published_events=Count(
            "id", filter=models.Q(status=SchoolEvent.Status.PUBLISHED)
        ),
        open_registrations=Count("registrations", distinct=True),
        sponsor_commitment_count=Count("sponsor_commitments", distinct=True),
        sponsorship_total=Sum("sponsor_commitments__pledged_amount"),
    )
    return {
        "events_total": totals.get("events_total") or 0,
        "published_events": totals.get("published_events") or 0,
        "open_registrations": totals.get("open_registrations") or 0,
        "sponsor_commitments": totals.get("sponsor_commitment_count") or 0,
        "sponsorship_total": totals.get("sponsorship_total") or 0,
    }


@transaction.atomic
def register_for_tier(
    *,
    event: SchoolEvent,
    tier: EventTicketTier,
    purchaser,
    quantity: int = 1,
) -> EventRegistration:
    """Create a registration and increment sold qty with capacity enforcement.

    Tiers with ``capacity <= 0`` are treated as sold out (no unlimited bypass).
    Paid tiers land ``RESERVED``; free tiers land ``CONFIRMED``.
    """
    qty = max(int(quantity or 1), 1)
    # Lock the tier row so concurrent posts cannot oversell.
    locked = EventTicketTier.objects.select_for_update().get(pk=tier.pk)
    if locked.event_id != event.pk or not locked.is_active:
        raise TicketCapacityError("Ticket tier is not available.")
    remaining = locked.remaining_capacity
    if remaining < qty:
        raise TicketCapacityError(
            f"Only {remaining} ticket(s) remaining for this tier."
        )
    total_due = Decimal(str(locked.price or 0)) * qty
    status = (
        EventRegistration.Status.CONFIRMED
        if total_due <= 0
        else EventRegistration.Status.RESERVED
    )
    registration = EventRegistration.objects.create(
        event=event,
        ticket_tier=locked,
        purchaser=purchaser,
        attendee_name=purchaser.get_full_name() or purchaser.username,
        attendee_email=getattr(purchaser, "email", "") or "",
        quantity=qty,
        amount_due=total_due,
        amount_paid=Decimal("0.00"),
        status=status,
    )
    EventTicketTier.objects.filter(pk=locked.pk).update(
        sold_quantity=F("sold_quantity") + qty
    )
    return registration
