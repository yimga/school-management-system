from __future__ import annotations

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Q
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.accounts.decorators import parent_portal_required, role_required
from apps.accounts.models import User
from apps.communication.models import ContactRequest
from apps.people.models import StudentProfile

from .forms_contact_requests import ContactRequestAssignForm, ContactRequestCreateForm, ContactRequestUpdateStatusForm
from .services import guardian_student_links


TRIAGE_ROLES = {
    User.Role.SECRETARY,
    User.Role.EXECUTIVE_ASSISTANT,
    User.Role.VIRTUAL_ASSISTANT,
}


def _pick_triage_owner() -> User | None:
    triager = User.objects.filter(Q(role__in=TRIAGE_ROLES) | Q(roles__code__in=TRIAGE_ROLES)).distinct().first()
    if triager:
        return triager
    # fallback: any admin/staff
    return User.objects.filter(Q(is_superuser=True) | Q(role=User.Role.ADMIN)).distinct().first()


@parent_portal_required
@role_required(User.Role.PARENT)
def parent_contact_school(request: HttpRequest):
    links = guardian_student_links(request.user, results_only=False).select_related("student")
    students = [link.student for link in links]

    form = ContactRequestCreateForm(request.POST or None, request.FILES or None, parent=request.user, students=students)
    if request.method == "POST" and form.is_valid():
        triage_owner = _pick_triage_owner()
        desired_staff = form.cleaned_data.get("desired_staff")
        student = form.cleaned_data.get("student")

        contact = ContactRequest.objects.create(
            parent=request.user,
            student=student,
            contact_name=form.cleaned_data["contact_name"],
            contact_phone=form.cleaned_data.get("contact_phone", ""),
            contact_whatsapp=form.cleaned_data.get("contact_whatsapp", ""),
            contact_email=form.cleaned_data.get("contact_email", ""),
            audience=form.cleaned_data["audience"],
            preferred_channel=form.cleaned_data["preferred_channel"],
            subject=form.cleaned_data["subject"],
            message=form.cleaned_data["message"],
            desired_staff=desired_staff,
            triage_owner=triage_owner,
            status=ContactRequest.Status.OPEN,
        )

        for f in request.FILES.getlist("attachments"):
            contact.attachments.create(file=f, uploaded_by=request.user)

        messages.success(request, "Your request has been submitted. The school team will contact you soon.")
        return redirect("portal:parent_dashboard")

    return render(request, "parent/contact_school.html", {"form": form, "students": students})


def _can_triage(user: User) -> bool:
    if user.is_superuser:
        return True
    if getattr(user, "role", None) in TRIAGE_ROLES or getattr(user, "role", None) == User.Role.ADMIN:
        return True
    return user.roles.filter(code__in=list(TRIAGE_ROLES)).exists()


@staff_member_required
def staff_contact_request_list(request: HttpRequest):
    if not _can_triage(request.user):
        return HttpResponseForbidden("You are not authorized to manage contact requests.")

    status_filter = request.GET.get("status", "")
    mine = request.GET.get("mine", "")

    qs = ContactRequest.objects.select_related("parent", "student", "desired_staff", "assigned_to", "triage_owner")
    if status_filter:
        qs = qs.filter(status=status_filter)
    if mine == "1":
        qs = qs.filter(Q(triage_owner=request.user) | Q(assigned_to=request.user))

    return render(
        request,
        "staff/contact_requests_list.html",
        {
            "requests": qs.order_by("-created_at"),
            "status_filter": status_filter,
            "status_options": [("", "All")] + list(ContactRequest.Status.choices),
            "mine": mine,
        },
    )


@staff_member_required
def staff_contact_request_detail(request: HttpRequest, request_id):
    if not _can_triage(request.user):
        return HttpResponseForbidden("You are not authorized to manage contact requests.")

    ticket = get_object_or_404(ContactRequest.objects.select_related("parent", "student", "desired_staff", "assigned_to", "triage_owner"), id=request_id)

    assign_form = ContactRequestAssignForm(request.POST or None, instance=ticket)
    status_form = ContactRequestUpdateStatusForm(request.POST or None, instance=ticket)

    if request.method == "POST":
        action = request.POST.get("action") or ""
        if action == "assign" and assign_form.is_valid():
            ticket.assigned_to = assign_form.cleaned_data["assigned_to"]
            ticket.triage_notes = assign_form.cleaned_data.get("triage_notes", "")
            ticket.status = ContactRequest.Status.ASSIGNED if ticket.assigned_to_id else ticket.status
            ticket.triage_owner = ticket.triage_owner or request.user
            ticket.save(update_fields=["assigned_to", "triage_notes", "status", "triage_owner", "updated_at"])
            messages.success(request, "Assignment saved.")
            return redirect("portal:staff_contact_request_detail", request_id=str(ticket.id))

        if action == "status" and status_form.is_valid():
            ticket.status = status_form.cleaned_data["status"]
            ticket.resolution_notes = status_form.cleaned_data.get("resolution_notes", "")
            if ticket.status in (ContactRequest.Status.RESOLVED, ContactRequest.Status.CLOSED) and not ticket.closed_at:
                ticket.closed_at = timezone.now()
            ticket.save(update_fields=["status", "resolution_notes", "closed_at", "updated_at"])
            messages.success(request, "Status updated.")
            return redirect("portal:staff_contact_request_detail", request_id=str(ticket.id))

    return render(
        request,
        "staff/contact_requests_detail.html",
        {
            "ticket": ticket,
            "assign_form": assign_form,
            "status_form": status_form,
            "back_url": reverse("portal:staff_contact_request_list"),
        },
    )

