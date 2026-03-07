from decimal import Decimal

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.school_events.models import EventRegistration, EventTicketTier, SchoolEvent
from apps.school_events.services import event_operations_snapshot


def _current_school(request):
    return getattr(request, "school", None)


@login_required
def event_hub(request):
    school = _current_school(request)
    if school is None:
        return HttpResponseForbidden("Tenant context required.")
    events = (
        SchoolEvent.objects.filter(school=school)
        .select_related("venue")
        .prefetch_related("ticket_tiers", "sponsor_commitments__sponsor")
        .order_by("start_at", "title")
    )
    return render(
        request,
        "school_events/event_hub.html",
        {
            "school": school,
            "events": events,
            "snapshot": event_operations_snapshot(school),
        },
    )


@login_required
def event_detail(request, slug):
    school = _current_school(request)
    if school is None:
        return HttpResponseForbidden("Tenant context required.")
    event = get_object_or_404(
        SchoolEvent.objects.select_related("venue").prefetch_related("ticket_tiers", "sponsor_commitments__sponsor"),
        school=school,
        slug=slug,
    )
    return render(request, "school_events/event_detail.html", {"school": school, "event": event})


@login_required
@require_POST
def register_for_event(request, slug):
    school = _current_school(request)
    if school is None:
        return HttpResponseForbidden("Tenant context required.")
    event = get_object_or_404(SchoolEvent, school=school, slug=slug, status=SchoolEvent.Status.PUBLISHED)
    if not event.ticketing_enabled:
        return HttpResponseForbidden("Ticketing is not enabled for this event.")

    ticket_tier_id = request.POST.get("ticket_tier_id")
    quantity = max(int(request.POST.get("quantity", 1) or 1), 1)
    tier = get_object_or_404(EventTicketTier, event=event, pk=ticket_tier_id, is_active=True)
    total_due = Decimal(str(tier.price or 0)) * quantity
    status = EventRegistration.Status.CONFIRMED if total_due <= 0 else EventRegistration.Status.RESERVED
    EventRegistration.objects.create(
        event=event,
        ticket_tier=tier,
        purchaser=request.user,
        attendee_name=request.user.get_full_name() or request.user.username,
        attendee_email=request.user.email or "",
        quantity=quantity,
        amount_due=total_due,
        amount_paid=Decimal("0.00"),
        status=status,
    )
    tier.sold_quantity += quantity
    tier.save(update_fields=["sold_quantity", "updated_at"])
    return redirect("school_events:event_detail", slug=event.slug)

