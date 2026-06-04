"""
Operator support ticket form on manager host (batch 1356).
"""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods

from apps.communication.models import Message
from apps.portal.forms_support import SupportRequestForm
from apps.portal.views_support import SUPPORT_TICKET_SOFT_FAILURES, _pick_support_owner
from apps.schools.control_plane import require_control_plane_access
from apps.schools.models import School
from apps.schools.operator_report_render import render_manager_report_page


class ManagerSupportRequestForm(SupportRequestForm):
    school = forms.ModelChoiceField(
        queryset=School.objects.filter(is_active=True).order_by("name"),
        required=False,
        label=_("Tenant (optional)"),
        help_text=_(
            "Link this ticket to a school when the issue is tenant-specific. "
            "Leave blank for platform-wide operator requests."
        ),
    )


@login_required
@require_http_methods(["GET", "POST"])
@require_control_plane_access
def manager_support_request(request):
    next_url = request.GET.get("next") or request.POST.get("next") or ""
    if next_url and not url_has_allowed_host_and_scheme(next_url, {request.get_host()}):
        next_url = ""

    initial: dict = {}
    category = request.GET.get("type") or request.POST.get("category")
    if category:
        initial["category"] = category.upper()

    from apps.feedback.form_widgets import apply_bootstrap_form_styles

    form = ManagerSupportRequestForm(request.POST or None, initial=initial)
    apply_bootstrap_form_styles(form)
    if request.method == "POST" and form.is_valid():
        school = form.cleaned_data.get("school")
        subject_prefix = (
            "[Support]" if form.cleaned_data["category"] == "SUPPORT" else "[Feedback]"
        )
        subject = f"{subject_prefix} {form.cleaned_data['subject']}"
        body = (
            f"From: {request.user.get_full_name()} ({request.user.username})\n"
            f"Role: {getattr(request.user, 'role', '')}\n"
            f"Email: {request.user.email or 'N/A'}\n"
            f"Host: manager\n"
            f"Path: {request.path}\n"
            f"Next: {next_url or 'N/A'}\n\n"
            f"{form.cleaned_data['message']}"
        )
        ticket = None
        if school is not None:
            try:
                from django.utils import timezone

                from apps.siteconfig.models_feature_controls import GlobalSupportTicket

                deflection_ack = request.POST.get("deflection_acknowledged") == "1"
                ticket_metadata = {
                    "host": "manager",
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
                    priority=GlobalSupportTicket.Priority.HIGH,
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
                        surface="manager_support_ticket",
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

            transaction.on_commit(_created_hooks)

        messages.success(
            request, str(_("Thanks! Your message has been sent to the support team."))
        )
        if next_url:
            return redirect(next_url)
        return redirect("manager_help_center")

    return render_manager_report_page(
        request,
        body_template="schools/partials/manager_support_request_body.html",
        context={
            "form": form,
            "next_url": next_url,
            "help_center_url": reverse("manager_help_center"),
        },
        page_title=str(_("Support request")),
        page_archetype="contact-routing",
    )
