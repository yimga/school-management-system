"""
Bursar queue for offline payment intents (SFDP 1425).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
import csv
import io

from django.http import HttpRequest, HttpResponse, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST, require_GET

from apps.finance.models import OfflinePaymentIntent
from apps.finance.payment_orchestration import reconcile_offline_payment_intent
from apps.finance.views_common import _active_profile, finance_save_redirect

_BULK_APPROVE_MAX = 50


def _queued_intents_qs(request, profile):
    school = getattr(request, "school", None)
    qs = (
        OfflinePaymentIntent.objects.filter(
            status=OfflinePaymentIntent.Status.QUEUED_REVIEW,
            invoice__profile=profile,
        )
        .select_related("invoice", "invoice__student", "recorded_by")
        .order_by("-created_at")
    )
    if school is not None:
        qs = qs.filter(invoice__school_id=school.pk)
    return qs


@staff_member_required(login_url=settings.LOGIN_URL)
def offline_payment_intent_queue(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    qs = _queued_intents_qs(request, profile)
    paginator = Paginator(qs, 25)
    page_obj = paginator.get_page(request.GET.get("page") or 1)

    return render(
        request,
        "finance/offline_payment_intent_queue.html",
        {
            "page_obj": page_obj,
            "profile": profile,
        },
    )


@staff_member_required(login_url=settings.LOGIN_URL)
@require_POST
def offline_payment_intent_approve(request: HttpRequest, intent_id: int):
    from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

    blocked = block_if_wind_down_commerce(request)
    if blocked is not None:
        return blocked
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    intent = get_object_or_404(
        OfflinePaymentIntent.objects.select_related("invoice"),
        pk=intent_id,
        invoice__profile=profile,
        status=OfflinePaymentIntent.Status.QUEUED_REVIEW,
    )
    school = getattr(request, "school", None)
    if school is not None and intent.invoice.school_id != school.pk:
        return HttpResponseForbidden("Tenant mismatch.")

    try:
        payment = reconcile_offline_payment_intent(intent, reconciled_by=request.user)
        from apps.finance.payment_notification_intent import dispatch_payment_received_intent

        dispatch_payment_received_intent(school=intent.invoice.school, payment=payment)
        messages.success(request, "Offline payment approved and posted to the ledger.")
    except ValueError as exc:
        messages.error(request, str(exc))

    return finance_save_redirect(request, "finance:offline_payment_intent_queue")


@staff_member_required(login_url=settings.LOGIN_URL)
@require_POST
def offline_payment_intent_bulk_approve(request: HttpRequest):
    """Approve up to 50 queued intents per POST (SFDP 1445)."""
    from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

    blocked = block_if_wind_down_commerce(request)
    if blocked is not None:
        return blocked
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    raw_ids = request.POST.getlist("intent_ids")
    if not raw_ids:
        messages.error(request, "Select at least one offline payment to approve.")
        return finance_save_redirect(request, "finance:offline_payment_intent_queue")

    try:
        intent_ids = [int(x) for x in raw_ids[:_BULK_APPROVE_MAX]]
    except (TypeError, ValueError):
        messages.error(request, "Invalid selection.")
        return finance_save_redirect(request, "finance:offline_payment_intent_queue")

    school = getattr(request, "school", None)
    approved = 0
    failed = 0
    for intent_id in intent_ids:
        intent = (
            OfflinePaymentIntent.objects.select_related("invoice")
            .filter(
                pk=intent_id,
                invoice__profile=profile,
                status=OfflinePaymentIntent.Status.QUEUED_REVIEW,
            )
            .first()
        )
        if intent is None:
            failed += 1
            continue
        if school is not None and intent.invoice.school_id != school.pk:
            failed += 1
            continue
        try:
            payment = reconcile_offline_payment_intent(intent, reconciled_by=request.user)
            from apps.finance.payment_notification_intent import dispatch_payment_received_intent

            dispatch_payment_received_intent(school=intent.invoice.school, payment=payment)
            approved += 1
        except ValueError:
            failed += 1

    if approved:
        messages.success(request, f"Approved {approved} offline payment(s).")
    if failed:
        messages.warning(request, f"Skipped or failed {failed} item(s).")
    return finance_save_redirect(request, "finance:offline_payment_intent_queue")


@staff_member_required(login_url=settings.LOGIN_URL)
@require_GET
def offline_payment_intent_queue_export(request: HttpRequest):
    """CSV export of queued offline intents for audit (SFDP 1445)."""
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        ["intent_id", "invoice_id", "amount", "currency", "created_at", "recorded_by_id"]
    )
    for intent in _queued_intents_qs(request, profile)[:500]:
        inv = intent.invoice
        writer.writerow(
            [
                intent.pk,
                inv.pk if inv else "",
                str(intent.amount),
                # OfflinePaymentIntent has no per-intent currency field — the
                # currency is the school's compliance-profile currency (already
                # resolved + non-None above). The former intent.currency_code
                # access raised AttributeError, 500-ing this CSV export.
                profile.currency_code or "",
                intent.created_at.isoformat() if intent.created_at else "",
                intent.recorded_by_id or "",
            ]
        )
    response = HttpResponse(buffer.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="offline_intents_queue.csv"'
    return response
