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
from apps.compliance.tenant_scope import get_compliance_scope_school


def _is_data_rights_operator(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.is_staff
        or user.has_perm("compliance.manage_data_rights")
    )


def _operator_scoped(request, model):
    """v4.01 SECURITY — scope a data-rights queryset to the operator's tenant.

    Compliance models have no RLS, so a bare ``Model.objects`` lets any tenant
    operator read/mutate another tenant's data-rights records by PK. Platform
    control-plane operators (no bound school) legitimately see all tenants; a
    tenant-scoped operator sees only their own school. ``get_compliance_scope_school``
    raises PermissionDenied when there is neither a school context nor
    control-plane access, so this fails closed.
    """
    school = get_compliance_scope_school(request)
    qs = model.objects.all()
    if school is None:
        return qs
    return qs.filter(school=school)


@login_required
@user_passes_test(_is_data_rights_operator)
@require_GET
def data_rights_queue(request):
    """List Export + Erase requests with optional status / overdue filters."""
    status = (request.GET.get("status") or "").strip().lower()
    overdue_only = request.GET.get("overdue") == "1"
    now = timezone.now()

    exports = _operator_scoped(request, ExportJob).select_related(
        "requested_by", "school"
    ).order_by("-created_at")
    erases = _operator_scoped(request, EraseRequest).select_related(
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
    erase = get_object_or_404(_operator_scoped(request, EraseRequest), pk=pk)
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
    erase = get_object_or_404(_operator_scoped(request, EraseRequest), pk=pk)
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
    # v4.01 COMPLIANCE — completing an erase MUST actually scrub the subject's
    # PII. Previously this flipped status→COMPLETED without erasing anything,
    # recording the Art.17 obligation as discharged while the data remained.
    # Route through the single sanctioned scrub-and-complete transition.
    from apps.compliance.gdpr_services import fulfill_pending_erasure

    erase = get_object_or_404(_operator_scoped(request, EraseRequest), pk=pk)
    if erase.status != EraseRequest.Status.APPROVED:
        messages.warning(request, f"Erase request {pk} must be approved before completing.")
        return _back_to_queue(request)
    result = fulfill_pending_erasure(erase.pk, fulfilled_by_user_id=getattr(request.user, "id", None))
    if result.get("ok"):
        messages.success(request, f"Erase request {pk} fulfilled — PII scrubbed and marked complete.")
    else:
        messages.error(request, f"Erase request {pk} NOT completed: {result.get('error') or 'scrub failed'}.")
    return _back_to_queue(request)


@login_required
@user_passes_test(_is_data_rights_operator)
@require_POST
def complete_export(request, pk):
    job = get_object_or_404(_operator_scoped(request, ExportJob), pk=pk)
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
