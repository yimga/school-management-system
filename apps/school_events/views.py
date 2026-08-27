from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.accounts.decorators import require_permission
from apps.school_events.models import EventRegistration, EventTicketTier, SchoolEvent
from apps.school_events.services import (
    TicketCapacityError,
    ensure_ticket_invoice,
    event_operations_snapshot,
    register_for_tier,
)


def _current_school(request):
    return getattr(request, "school", None)


def _can_view_console(request) -> bool:
    """Same additive union the decorator applies, for the template flag.

    permission_access is the canonical resolver behind @require_permission;
    using it here keeps the in-body check and the decorator from drifting
    apart, which is how a page ends up refusing what its own gate allows.
    """
    from apps.accounts.effective_access import permission_access

    return permission_access(
        getattr(request, "user", None),
        _current_school(request),
        ("events.view", "events.manage"),
    )


@login_required
# The console: EVERY event including drafts, plus event_operations_snapshot.
# @login_required alone meant a student or parent could open it.
@require_permission("events.view", "events.manage")
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
    # Deliberately NOT gated on events.view: register_for_event redirects here
    # after a purchase, so gating it would break ticket buying for the parents
    # and students it exists for. What IS restricted is what only staff should
    # see -- an unpublished event, and the sponsor pledge amounts.
    can_view_console = _can_view_console(request)
    queryset = SchoolEvent.objects.select_related("venue").prefetch_related(
        "ticket_tiers", "sponsor_commitments__sponsor"
    )
    if not can_view_console:
        queryset = queryset.filter(status=SchoolEvent.Status.PUBLISHED)
    event = get_object_or_404(queryset, school=school, slug=slug)
    return render(
        request,
        "school_events/event_detail.html",
        {
            "school": school,
            "event": event,
            # Drives the sponsor block, which lists every sponsor's pledged amount.
            "can_view_console": can_view_console,
        },
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

    # quantity had a try/except and the tier id did not. get_object_or_404 only
    # converts DoesNotExist into an Http404 -- an unparseable pk raises ValueError
    # out of AutoField.get_prep_value, so `ticket_tier_id=abc` was an unhandled
    # 500 and a Sentry event instead of a form error.
    try:
        ticket_tier_id = int(request.POST.get("ticket_tier_id") or "")
    except (TypeError, ValueError):
        messages.error(request, _("Choose a ticket type."))
        return redirect("school_events:event_detail", slug=event.slug)
    try:
        quantity = max(int(request.POST.get("quantity", 1) or 1), 1)
    except (TypeError, ValueError):
        quantity = 1
    tier = get_object_or_404(
        EventTicketTier, event=event, pk=ticket_tier_id, is_active=True
    )
    try:
        registration = register_for_tier(
            event=event,
            tier=tier,
            purchaser=request.user,
            quantity=quantity,
        )
        messages.success(request, _("Registration recorded."))
    except TicketCapacityError as exc:
        messages.error(request, str(exc))
        return redirect("school_events:event_detail", slug=event.slug)
    # A paid tier lands RESERVED with amount_due set. Nothing used to raise the
    # matching AR invoice, so the family had nothing to pay, the payment webhook
    # had no invoice to settle, and expire_stale_reservations cancelled the hold
    # 45 minutes later. Best-effort: a finance misconfiguration must not lose the
    # registration the family just made.
    if registration.status == EventRegistration.Status.RESERVED:
        if ensure_ticket_invoice(registration=registration) is None:
            messages.warning(
                request,
                _(
                    "Your place is held, but we could not raise the invoice "
                    "automatically \u2014 please contact the school office to pay."
                ),
            )
    return redirect("school_events:event_detail", slug=event.slug)
