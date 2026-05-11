"""
Pass 9.C: operator-facing queue for ExportJob + EraseRequest with approve /
reject / complete actions and SLA tracking. Read-only listing is the v1
surface; mutation goes through three small POST endpoints that the row's
form-buttons invoke.

Only superusers + staff with `compliance.manage_data_rights` can use this
queue — same gate as the existing GDPR views.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.db.models import Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from apps.compliance.models import EraseRequest, ExportJob


def _is_data_rights_operator(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.is_staff
        or user.has_perm("compliance.manage_data_rights")
    )


@login_required
@user_passes_test(_is_data_rights_operator)
@require_GET
def data_rights_queue(request):
    """List Export + Erase requests with optional status / overdue filters."""
    status = (request.GET.get("status") or "").strip().lower()
    overdue_only = request.GET.get("overdue") == "1"
    now = timezone.now()

    exports = ExportJob.objects.select_related("requested_by", "school").order_by(
        "-created_at"
    )
    erases = EraseRequest.objects.select_related(
        "requested_by", "school", "subject_user"
    ).order_by("-created_at")

    if status:
        exports = exports.filter(status=status)
        erases = erases.filter(status=status)
    if overdue_only:
        exports = exports.filter(due_at__lt=now).exclude(
            status=ExportJob.Status.COMPLETED
        )
        erases = erases.filter(due_at__lt=now).filter(
            Q(status=EraseRequest.Status.PENDING) | Q(status=EraseRequest.Status.APPROVED)
        )

    return render(
        request,
        "compliance/data_rights_queue.html",
        {
            "exports": exports[:200],
            "erases": erases[:200],
            "status_filter": status,
            "overdue_only": overdue_only,
            "now": now,
        },
    )


@login_required
@user_passes_test(_is_data_rights_operator)
@require_POST
def approve_erase(request, pk):
    erase = get_object_or_404(EraseRequest, pk=pk)
    if erase.status == EraseRequest.Status.PENDING:
        erase.status = EraseRequest.Status.APPROVED
        erase.save(update_fields=["status"])
        messages.success(request, f"Erase request {pk} approved.")
    else:
        messages.warning(request, f"Erase request {pk} is not pending.")
    return _back_to_queue(request)


@login_required
@user_passes_test(_is_data_rights_operator)
@require_POST
def reject_erase(request, pk):
    erase = get_object_or_404(EraseRequest, pk=pk)
    if erase.status in (EraseRequest.Status.PENDING, EraseRequest.Status.APPROVED):
        erase.status = EraseRequest.Status.REJECTED
        erase.completed_at = timezone.now()
        erase.save(update_fields=["status", "completed_at"])
        messages.success(request, f"Erase request {pk} rejected.")
    else:
        messages.warning(request, f"Erase request {pk} cannot be rejected from {erase.status}.")
    return _back_to_queue(request)


@login_required
@user_passes_test(_is_data_rights_operator)
@require_POST
def complete_erase(request, pk):
    erase = get_object_or_404(EraseRequest, pk=pk)
    if erase.status == EraseRequest.Status.APPROVED:
        erase.status = EraseRequest.Status.COMPLETED
        erase.completed_at = timezone.now()
        erase.save(update_fields=["status", "completed_at"])
        messages.success(request, f"Erase request {pk} marked complete.")
    else:
        messages.warning(request, f"Erase request {pk} must be approved before completing.")
    return _back_to_queue(request)


@login_required
@user_passes_test(_is_data_rights_operator)
@require_POST
def complete_export(request, pk):
    job = get_object_or_404(ExportJob, pk=pk)
    if job.status != ExportJob.Status.COMPLETED:
        job.status = ExportJob.Status.COMPLETED
        job.completed_at = timezone.now()
        job.save(update_fields=["status", "completed_at"])
        messages.success(request, f"Export job {pk} marked complete.")
    else:
        messages.info(request, f"Export job {pk} was already complete.")
    return _back_to_queue(request)


def _back_to_queue(request):
    referer = request.META.get("HTTP_REFERER")
    if referer:
        return HttpResponseRedirect(referer)
    try:
        return redirect(reverse("compliance:data_rights_queue"))
    except Exception:  # noqa: BLE001
        return redirect("/")
