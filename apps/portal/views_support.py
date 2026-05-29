from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, transaction
from django.db.models import Q
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme

from apps.accounts.models import User
from apps.communication.models import Message


from .forms_support import SupportRequestForm

SUPPORT_TICKET_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    ImportError,
    LookupError,
    TypeError,
    ValueError,
)


def _pick_support_owner() -> User | None:
    # v4.00.43 — prefer the live on-call user over the role-based fallback chain.
    try:
        from apps.siteconfig.support_on_call import get_active_on_call_user

        on_call = get_active_on_call_user()
        if on_call is not None:
            return on_call
    except (ImportError, LookupError, AttributeError):
        pass

    preferred_roles = [
        User.Role.IT_ADMIN,
    ]
    fallback_roles = [
        User.Role.ADMIN,
        User.Role.SUPERADMIN,
        User.Role.LEADERSHIP,
    ]

    qs = User.objects.filter(
        Q(role__in=preferred_roles) | Q(roles__code__in=preferred_roles)
    ).distinct()
    if qs.exists():
        return qs.order_by("id").first()

    qs = User.objects.filter(
        Q(role__in=fallback_roles) | Q(roles__code__in=fallback_roles)
    ).distinct()
    if qs.exists():
        return qs.order_by("id").first()

    qs = User.objects.filter(Q(is_superuser=True) | Q(is_staff=True)).distinct()
    return qs.order_by("id").first()


@login_required
def support_help_hub(request):
    """
    Legacy URL — canonical tenant help front door is feedback:help_center.
    Preserves deep links; merges ticket context on the unified hub.
    """
    from django.http import HttpResponseRedirect
    from django.urls import reverse

    target = reverse("feedback:help_center")
    section = (request.GET.get("section") or "support").strip()
    if section:
        target = f"{target}?section={section}"
    return HttpResponseRedirect(target)


@login_required
def support_request(request):
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if next_url and not url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        next_url = ""

    initial = {}
    category = request.GET.get("type") or request.POST.get("category")
    if category:
        initial["category"] = category.upper()

    form = SupportRequestForm(request.POST or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        school = getattr(request, "school", None)
        subject_prefix = (
            "[Support]" if form.cleaned_data["category"] == "SUPPORT" else "[Feedback]"
        )
        subject = f"{subject_prefix} {form.cleaned_data['subject']}"
        body = (
            f"From: {request.user.get_full_name()} ({request.user.username})\n"
            f"Role: {request.user.role}\n"
            f"Email: {request.user.email or 'N/A'}\n"
            f"Path: {request.path}\n"
            f"Next: {next_url or 'N/A'}\n\n"
            f"{form.cleaned_data['message']}"
        )
        # Global support ticket (command center) + link to staff Message for traceability
        ticket = None
        if school:
            try:
                from apps.portal.runtime_helpers import get_policy_for_request
                from apps.siteconfig.models_feature_controls import GlobalSupportTicket

                policy = get_policy_for_request(request)
                plan_slug = (policy.get("plan_slug") or "").strip().lower()
                country_code = (policy.get("country_code") or "")[:2]
                priority = GlobalSupportTicket.Priority.NORMAL
                if plan_slug in ("powerhouse", "enterprise", "pro"):
                    priority = GlobalSupportTicket.Priority.HIGH
                from django.utils import timezone

                deflection_ack = request.POST.get("deflection_acknowledged") == "1"
                ticket_metadata = {
                    "country_code": country_code,
                    "plan_slug": plan_slug,
                    "category": form.cleaned_data["category"],
                    "deflection_acknowledged": deflection_ack,
                }
                if deflection_ack:
                    ticket_metadata["deflected_at"] = timezone.now().isoformat()
                ticket = GlobalSupportTicket.objects.create(
                    school=school,
                    user=request.user,
                    subject=subject,
                    body=body,
                    priority=priority,
                    status=GlobalSupportTicket.Status.OPEN,
                    metadata=ticket_metadata,
                )
                try:
                    from apps.feedback.models import SupportDeflectionEvent
                    from apps.portal.support_deflection import record_deflection_event

                    query_text = " ".join(
                        [
                            form.cleaned_data.get("subject") or "",
                            form.cleaned_data.get("message") or "",
                        ]
                    ).strip()
                    record_deflection_event(
                        request,
                        query_text=query_text,
                        articles=[],
                        outcome=(
                            SupportDeflectionEvent.Outcome.DISMISSED
                            if deflection_ack
                            else SupportDeflectionEvent.Outcome.SUBMITTED
                        ),
                        surface="support_ticket",
                    )
                except SUPPORT_TICKET_SOFT_FAILURES:
                    pass
            except SUPPORT_TICKET_SOFT_FAILURES:
                ticket = None
        recipient = _pick_support_owner()
        msg = None
        if recipient:
            from apps.communication.comms_locale import locale_target_for_user

            msg = Message.objects.create(
                sender=request.user,
                recipient=recipient,
                subject=subject,
                body=body,
                locale_target=locale_target_for_user(recipient),
            )
        if ticket is not None and msg is not None:
            try:
                md = dict(ticket.metadata or {})
                md["communication_message_id"] = msg.pk
                type(ticket).objects.filter(pk=ticket.pk).update(metadata=md)
            except SUPPORT_TICKET_SOFT_FAILURES:
                pass
        if ticket is not None:
            tid = str(ticket.pk)
            rid = recipient.pk if recipient else None

            def _created_hooks() -> None:
                try:
                    from apps.siteconfig.support_ticket_hooks import (
                        run_support_ticket_created_hooks,
                    )

                    run_support_ticket_created_hooks(
                        tid, primary_recipient_id=rid
                    )
                except SUPPORT_TICKET_SOFT_FAILURES:
                    pass
                # v4.00.43 — AI triage; soft-fails when AI gateway unavailable.
                try:
                    from apps.siteconfig.support_ai_triage import run_ai_triage

                    run_ai_triage(ticket, request=None)
                except SUPPORT_TICKET_SOFT_FAILURES:
                    pass

            transaction.on_commit(_created_hooks)
        messages.success(
            request, "Thanks! Your message has been sent to the support team."
        )
        if next_url:
            return redirect(next_url)
        return redirect("portal:portal_home")

    return render(
        request,
        "portal/support_request.html",
        {
            "form": form,
            "next_url": next_url,
        },
    )


@login_required
def support_ticket_detail(request, ticket_id):
    """
    Submitter-only: threaded conversation (public replies) and optional CSAT after resolution.
    """
    school = getattr(request, "school", None)
    if school is None:
        return HttpResponseForbidden(
            "School context is required to view this ticket."
        )
    try:
        from apps.siteconfig.models_feature_controls import (
            GlobalSupportTicket,
            GlobalSupportTicketReply,
        )
    except SUPPORT_TICKET_SOFT_FAILURES:
        return HttpResponseForbidden("Support tickets are unavailable.")

    ticket = get_object_or_404(
        GlobalSupportTicket.objects.prefetch_related("thread_replies__author"),
        pk=ticket_id,
        school=school,
        user=request.user,
    )

    if request.method == "POST":
        action = (request.POST.get("action") or "").strip().lower()
        if action == "followup":
            body = (request.POST.get("followup_body") or "").strip()
            if body:
                GlobalSupportTicketReply.objects.create(
                    ticket=ticket,
                    author=request.user,
                    body=body[:32000],
                    visibility=GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE,
                )
                try:
                    from apps.siteconfig.support_ticket_hooks import (
                        run_support_ticket_reply_hooks,
                    )

                    run_support_ticket_reply_hooks(
                        str(ticket.pk),
                        actor_id=request.user.pk,
                        visibility=GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE,
                        reply_body=body[:32000],
                    )
                except SUPPORT_TICKET_SOFT_FAILURES:
                    pass
                messages.success(request, "Your message was added to the ticket.")
            return redirect("portal:support_ticket_detail", ticket_id=ticket.pk)

        if action == "csat":
            if ticket.status not in (
                GlobalSupportTicket.Status.RESOLVED,
                GlobalSupportTicket.Status.CLOSED,
            ):
                messages.error(request, "CSAT is only available after the ticket is resolved.")
            elif ticket.csat_score is not None:
                messages.info(request, "You already submitted feedback for this ticket.")
            else:
                try:
                    score = int(request.POST.get("csat_score", "0"))
                except (TypeError, ValueError):
                    score = 0
                if score < 1 or score > 5:
                    messages.error(request, "Please choose a rating from 1 to 5.")
                else:
                    from django.utils import timezone

                    ticket.csat_score = score
                    ticket.csat_comment = (request.POST.get("csat_comment") or "")[
                        :2000
                    ]
                    ticket.csat_submitted_at = timezone.now()
                    ticket.save(
                        update_fields=[
                            "csat_score",
                            "csat_comment",
                            "csat_submitted_at",
                            "updated_at",
                        ]
                    )
                    try:
                        from apps.siteconfig.support_ticket_hooks import (
                            run_support_ticket_csat_hooks,
                        )

                        run_support_ticket_csat_hooks(
                            str(ticket.pk), actor_id=request.user.pk
                        )
                    except SUPPORT_TICKET_SOFT_FAILURES:
                        pass
                    messages.success(request, "Thank you for your feedback.")
            return redirect("portal:support_ticket_detail", ticket_id=ticket.pk)

    public_replies = [
        r
        for r in ticket.thread_replies.all()
        if r.visibility == GlobalSupportTicketReply.Visibility.SUBMITTER_VISIBLE
    ]
    show_csat = ticket.status in (
        GlobalSupportTicket.Status.RESOLVED,
        GlobalSupportTicket.Status.CLOSED,
    ) and ticket.csat_score is None

    return render(
        request,
        "portal/support_ticket_detail.html",
        {
            "ticket": ticket,
            "public_replies": public_replies,
            "show_csat": show_csat,
        },
    )
