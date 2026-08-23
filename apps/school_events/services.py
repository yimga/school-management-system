from datetime import timedelta
from decimal import Decimal

from django.db import models, transaction
from django.db.models import Count, F, Sum
from django.utils import timezone

from apps.school_events.models import (
    EventRegistration,
    EventSponsorCommitment,
    EventTicketTier,
    SchoolEvent,
)


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
    # THREE aggregates, not one. Spanning `registrations` AND
    # `sponsor_commitments` in a single aggregate makes SQL evaluate the cross
    # product, so an event with R registrations and S commitments contributes
    # R*S rows: Count("id") returned R*S instead of 1, and -- the one that
    # matters -- Sum of the pledged amounts was multiplied by R. A gala with two
    # 100 sponsors and forty ticket sales reported 8,000 of sponsorship.
    # distinct=True saves a COUNT but cannot save a SUM: it would dedupe equal
    # AMOUNTS, so two sponsors pledging 100 each would total 100.
    events = SchoolEvent.objects.filter(school=school)
    event_totals = events.aggregate(
        events_total=Count("id"),
        published_events=Count(
            "id", filter=models.Q(status=SchoolEvent.Status.PUBLISHED)
        ),
    )
    registration_total = EventRegistration.objects.filter(
        event__school=school
    ).count()
    sponsorship = EventSponsorCommitment.objects.filter(
        event__school=school
    ).aggregate(
        commitment_count=Count("id"),
        pledged_total=Sum("pledged_amount"),
    )
    return {
        "events_total": event_totals.get("events_total") or 0,
        "published_events": event_totals.get("published_events") or 0,
        "open_registrations": registration_total,
        "sponsor_commitments": sponsorship.get("commitment_count") or 0,
        "sponsorship_total": sponsorship.get("pledged_total") or 0,
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


class RegistrationStateError(Exception):
    """Raised when a registration is not in the expected status for an action."""


@transaction.atomic
def confirm_registration_payment(
    *,
    registration: EventRegistration,
    amount=None,
    method: str = "cash",
) -> EventRegistration:
    """Mark a RESERVED registration paid (cash/manual) and move to CONFIRMED.

    Metric #13: closes the unpaid-hold leak without requiring a live PSP.
    Idempotent when already CONFIRMED.
    """
    locked = EventRegistration.objects.select_for_update().get(pk=registration.pk)
    if locked.status == EventRegistration.Status.CONFIRMED:
        return locked
    if locked.status != EventRegistration.Status.RESERVED:
        raise RegistrationStateError(
            f"Cannot confirm payment from status {locked.status!r}."
        )
    paid = Decimal(str(amount if amount is not None else locked.amount_due or 0))
    if paid < 0:
        raise RegistrationStateError("amount must be non-negative")
    meta = dict(locked.metadata or {})
    meta["payment_method"] = (method or "cash").strip().lower() or "cash"
    meta["paid_at"] = timezone.now().isoformat()
    locked.amount_paid = paid
    locked.status = EventRegistration.Status.CONFIRMED
    locked.metadata = meta
    locked.save(update_fields=["amount_paid", "status", "metadata", "updated_at"])
    return locked


@transaction.atomic
def release_reservation(*, registration: EventRegistration) -> EventRegistration:
    """Cancel a RESERVED hold and restore tier capacity.

    Metric #13: unpaid RESERVED rows must not permanently consume sold_quantity.
    """
    locked = EventRegistration.objects.select_for_update().get(pk=registration.pk)
    if locked.status == EventRegistration.Status.CANCELED:
        return locked
    if locked.status != EventRegistration.Status.RESERVED:
        raise RegistrationStateError(
            f"Only RESERVED holds can be released (got {locked.status!r})."
        )
    qty = max(int(locked.quantity or 1), 1)
    tier_id = locked.ticket_tier_id
    locked.status = EventRegistration.Status.CANCELED
    meta = dict(locked.metadata or {})
    meta["released_at"] = timezone.now().isoformat()
    locked.metadata = meta
    locked.save(update_fields=["status", "metadata", "updated_at"])
    if tier_id:
        tier = EventTicketTier.objects.select_for_update().get(pk=tier_id)
        new_sold = max(int(tier.sold_quantity or 0) - qty, 0)
        EventTicketTier.objects.filter(pk=tier_id).update(sold_quantity=new_sold)
    return locked


def expire_stale_reservations(
    *,
    older_than_minutes: int = 45,
    limit: int = 500,
    school=None,
) -> int:
    """Release unpaid RESERVED holds older than ``older_than_minutes``.

    Metric #13: prevents abandoned holds from permanently consuming capacity
    when cash settle / PSP confirm never arrives.
    """
    minutes = max(int(older_than_minutes or 45), 1)
    cutoff = timezone.now() - timedelta(minutes=minutes)
    qs = EventRegistration.objects.filter(
        status=EventRegistration.Status.RESERVED,
        created_at__lt=cutoff,
    ).order_by("created_at")
    if school is not None:
        qs = qs.filter(event__school=school)
    released = 0
    for registration in qs[: max(int(limit or 500), 1)]:
        try:
            release_reservation(registration=registration)
            released += 1
        except RegistrationStateError:
            continue
    return released


def confirm_registration_from_psp(
    *,
    registration_id: int,
    school,
    amount=None,
    method: str = "psp",
    reference: str = "",
) -> EventRegistration:
    """Confirm a RESERVED registration after a successful PSP webhook.

    Looks up by primary key; stores the PSP reference in metadata. Live merchant
    capture remains EXTERNAL — this only closes the in-repo ticket state machine.
    """
    # ``school`` is REQUIRED and has no default on purpose. registration_id
    # arrives straight off a PSP webhook body -- payload, nested metadata, data
    # block, or the invoice's own metadata -- so an unscoped get(pk=...) let a
    # payment posted against one school's invoice confirm ANOTHER school's
    # ticket. Scoping through event__school makes a mismatch a DoesNotExist,
    # which the webhook caller reports without touching the posted Payment.
    # create_ticket_invoice_for_registration already guards the mirror-image
    # lookup this way; this path was missed.
    registration = EventRegistration.objects.get(
        pk=registration_id, event__school=school
    )
    confirmed = confirm_registration_payment(
        registration=registration,
        amount=amount,
        method=method or "psp",
    )
    if reference:
        meta = dict(confirmed.metadata or {})
        meta["psp_reference"] = str(reference)
        confirmed.metadata = meta
        confirmed.save(update_fields=["metadata", "updated_at"])
    return confirmed


@transaction.atomic
def create_ticket_invoice_for_registration(
    *,
    registration: EventRegistration,
    profile,
    academic_year,
    student=None,
):
    """Create an AR invoice linked to a RESERVED registration (Metric #13).

    Stores ``invoice_id`` on the registration metadata. Callers should pass
    ``event_registration_id`` on the webhook payload (or nested metadata) so
    ``_maybe_confirm_event_registration`` can settle the hold. Live PSP capture
    remains EXTERNAL.
    """
    from apps.finance.models import Invoice, InvoiceLine

    locked = EventRegistration.objects.select_for_update().get(pk=registration.pk)
    if locked.status != EventRegistration.Status.RESERVED:
        raise RegistrationStateError(
            f"Ticket invoice requires RESERVED status (got {locked.status!r})."
        )
    meta = dict(locked.metadata or {})
    existing_id = meta.get("invoice_id")
    if existing_id:
        try:
            # Scope the reuse lookup to the event's school so a stray/foreign
            # invoice_id can never resolve cross-tenant (falls through to a
            # fresh invoice below on mismatch).
            return Invoice.objects.get(
                pk=int(existing_id), school=getattr(locked.event, "school", None)
            )
        except (Invoice.DoesNotExist, TypeError, ValueError):
            pass

    amount = Decimal(str(locked.amount_due or 0))
    school = getattr(locked.event, "school", None)
    invoice = Invoice.objects.create(
        profile=profile,
        academic_year=academic_year,
        school=school,
        invoice_type=Invoice.InvoiceType.AR,
        status=Invoice.Status.ISSUED,
        student=student,
        total_amount=amount,
        balance_amount=amount,
        issued_date=timezone.now().date(),
        notes=(
            f"Event ticket registration {locked.pk} "
            f"(event_registration_id={locked.pk})"
        ),
    )
    InvoiceLine.objects.create(
        invoice=invoice,
        description=f"Event ticket x{locked.quantity}",
        quantity=Decimal(str(locked.quantity or 1)),
        unit_price=(amount / Decimal(str(max(int(locked.quantity or 1), 1)))).quantize(
            Decimal("0.01")
        ),
        amount=amount,
        fee_item=None,
    )
    meta["invoice_id"] = invoice.pk
    locked.metadata = meta
    locked.save(update_fields=["metadata", "updated_at"])
    return invoice
