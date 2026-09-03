"""Parent/guardian-facing online payment initiation (M26 slice 2).

Thin HTTP surface over
:func:`apps.finance.gateway_initiation.initiate_invoice_collection`: a parent
starts a mobile-money collection (MTN MoMo / M-Pesa / Orange Money / a redirect
PSP) against their own invoice.

Safety:
* **Flag-gated + INERT.** ``settings.RMC_GATEWAY_COLLECTION_ENABLED`` (default
  off via ``getattr``) — the route 404s until a deployment turns online
  collection on. Kept off in production until a school has live PSP credentials.
* **Auth.** Mirrors ``upload_payment_receipt``: the invoice is scoped to the
  requester's active compliance profile AND the requester must pass
  ``invoice_access`` or be the student's parent/guardian.
* **Never settles money.** Returns JSON describing the *request*; the ``Payment``
  is posted only when the provider's signed webhook confirms
  (``payment_provider_webhook`` -> ``record_provider_payment``).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_POST

from .gateway_initiation import initiate_invoice_collection
from .models import Invoice
from .views_common import _active_profile

logger = logging.getLogger(__name__)


@login_required
@require_POST
def initiate_online_payment(request, invoice_id):
    """Start an online gateway collection for ``invoice_id``. JSON response."""
    if not getattr(settings, "RMC_GATEWAY_COLLECTION_ENABLED", False):
        raise Http404("Online payment is not enabled.")

    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    invoice = get_object_or_404(
        Invoice.objects.select_related("student"), id=invoice_id, profile=profile
    )

    from apps.accounts.effective_access import invoice_access
    from apps.accounts.models import User
    from apps.people.models import StudentGuardian

    if not invoice_access(request.user, invoice_id):
        is_parent = getattr(request.user, "role", "") == User.Role.PARENT
        is_guardian = bool(
            invoice.student_id
            and StudentGuardian.objects.filter(  # tenant-isolation-allow: guardianship existence check on one (user, student) pair (reviewed 2026-09-03)
                guardian_user=request.user, student_id=invoice.student_id
            ).exists()
        )
        if not (is_parent and is_guardian):
            return HttpResponseForbidden(
                "You don't have permission to pay this invoice."
            )

    method_code = (request.POST.get("method_code") or "").strip()
    payer_phone = (request.POST.get("payer_phone") or "").strip() or None
    if not method_code:
        return JsonResponse(
            {"ok": False, "message": "Choose a payment method."}, status=400
        )

    result = initiate_invoice_collection(
        invoice=invoice,
        method_code=method_code,
        payer_phone=payer_phone,
    )
    logger.info(
        "Online payment initiation invoice=%s method=%s success=%s",
        invoice_id,
        method_code,
        bool(result.success),
    )

    # The invoice-page form posts ``_ui=1`` (no JS): surface a Django message and
    # redirect back. API callers omit it and get JSON.
    if request.POST.get("_ui"):
        from django.contrib import messages

        from .views_common import finance_detail_redirect

        if result.success:
            messages.success(
                request,
                result.message
                or "Payment request sent — check your phone to confirm.",
            )
        else:
            messages.error(
                request, result.message or "Could not start the online payment."
            )
        return finance_detail_redirect(request, invoice.id)

    return JsonResponse(
        {
            "ok": bool(result.success),
            "message": result.message,
            "status": (result.raw_response or {}).get("status"),
            "transaction_id": result.transaction_id,
        },
        status=200 if result.success else 400,
    )
