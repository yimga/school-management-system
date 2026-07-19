from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.school_events.models import EventTicketTier, SchoolEvent
from apps.school_events.services import (
    TicketCapacityError,
    event_operations_snapshot,
    register_for_tier,
)


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
        SchoolEvent.objects.select_related("venue").prefetch_related(
            "ticket_tiers", "sponsor_commitments__sponsor"
        ),
        school=school,
        slug=slug,
    )
    return render(
        request, "school_events/event_detail.html", {"school": school, "event": event}
    )


@login_required
@require_POST
def register_for_event(request, slug):
    school = _current_school(request)
    if school is None:
        return HttpResponseForbidden("Tenant context required.")
    event = get_object_or_404(
        SchoolEvent, school=school, slug=slug, status=SchoolEvent.Status.PUBLISHED
    )
    if not event.ticketing_enabled:
        return HttpResponseForbidden("Ticketing is not enabled for this event.")

    ticket_tier_id = request.POST.get("ticket_tier_id")
    try:
        quantity = max(int(request.POST.get("quantity", 1) or 1), 1)
    except (TypeError, ValueError):
        quantity = 1
    tier = get_object_or_404(
        EventTicketTier, event=event, pk=ticket_tier_id, is_active=True
    )
    try:
        register_for_tier(
            event=event,
            tier=tier,
            purchaser=request.user,
            quantity=quantity,
        )
        messages.success(request, _("Registration recorded."))
    except TicketCapacityError as exc:
        messages.error(request, str(exc))
    return redirect("school_events:event_detail", slug=event.slug)
