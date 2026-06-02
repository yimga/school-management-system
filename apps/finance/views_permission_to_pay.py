"""
Permission-to-pay micro-friction views (batch 1509).

Wires `apps.finance.permission_to_pay` to a real Django route surface so the
workflow is no longer a contract-only service.

Statelessness: this view does NOT persist requests. It demonstrates the
3-step state machine (open → guardian_approve → authorize) end-to-end via
session-backed storage of one in-flight request per session. Persistence
to a model is deferred until the model design is finalised.

Security posture:
- @login_required + role gate (finance / admin roles only can OPEN);
  guardian-approval step accepts the same role set (a future iteration
  could open it to the guardian portal once routed there)
- @require_school resolves tenant via the host pipeline
- audit emissions inherit the service's hashed-ID discipline
- amount / threshold are Decimal end-to-end; currency normalised to ISO
"""

from __future__ import annotations

import logging
from decimal import Decimal

from django.contrib.auth.decorators import login_required, user_passes_test
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.finance.payment_rail_adapter import register_manual_fallback, registry as payment_registry
from apps.schools.mixins import require_school

from .forms_permission_to_pay import OpenPermissionToPayForm, RecordGuardianApprovalForm
from .permission_to_pay import (
    PermissionToPayError,
    PermissionToPayRequest,
    authorize_payment,
    open_request,
    record_guardian_approval,
)


logger = logging.getLogger(__name__)

_SESSION_KEY = "permission_to_pay_inflight"


def _finance_roles_ok(user) -> bool:
    if not user or not user.is_authenticated:
        return False
    if getattr(user, "is_staff", False) or getattr(user, "is_superuser", False):
        return True
    role = (getattr(user, "role", "") or "").upper()
    # Canonical User.Role tokens only — "FINANCE" was a phantom role (no such
    # User.Role choice), so the intended FINANCE_STAFF was silently excluded.
    # (ACCOUNTANT is also a finance role but is intentionally NOT added here to
    # avoid widening the original grant; flag for owner if it should be included.)
    return role in {"ADMIN", "FINANCE_STAFF", "BURSAR", "PRINCIPAL", "LEADERSHIP"}  # role-string-allow: canonical-User.Role-finance-authz-tokens


def _serialize(req: PermissionToPayRequest) -> dict:
    return {
        "request_id": req.request_id,
        "tenant_id_hash": req.tenant_id_hash,
        "student_id_hash": req.student_id_hash,
        "event_code": req.event_code,
        "amount": str(req.amount),
        "currency": req.currency,
        "requires_guardian_approval": req.requires_guardian_approval,
        "state": req.state,
        "guardian_approval": (
            {
                "guardian_id": req.guardian_approval.guardian_id,
                "approved_at_iso": req.guardian_approval.approved_at_iso,
                "method": req.guardian_approval.method,
            }
            if req.guardian_approval
            else None
        ),
        "payment_result": (
            {
                "rail_id": req.payment_result.rail_id,
                "success": req.payment_result.success,
                "reference": req.payment_result.reference,
            }
            if req.payment_result
            else None
        ),
    }


def _deserialize(blob: dict) -> PermissionToPayRequest:
    from .permission_to_pay import GuardianApproval
    from apps.finance.payment_rail_adapter import PaymentResult

    return PermissionToPayRequest(
        request_id=blob["request_id"],
        tenant_id_hash=blob["tenant_id_hash"],
        student_id_hash=blob["student_id_hash"],
        event_code=blob["event_code"],
        amount=Decimal(blob["amount"]),
        currency=blob["currency"],
        requires_guardian_approval=blob["requires_guardian_approval"],
        guardian_approval=(
            GuardianApproval(**blob["guardian_approval"]) if blob.get("guardian_approval") else None
        ),
        payment_result=(
            PaymentResult(**blob["payment_result"]) if blob.get("payment_result") else None
        ),
        state=blob["state"],
    )


@login_required
@user_passes_test(_finance_roles_ok)
@require_school
@require_http_methods(["GET", "POST"])
def permission_to_pay_open(request):
    """Render or process the open-request form."""
    school = request.school
    tenant_id = str(school.pk) if school is not None else ""

    error = None
    form = OpenPermissionToPayForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        from apps.lifecycle.wind_down_guards import block_if_wind_down_commerce

        blocked = block_if_wind_down_commerce(request)
        if blocked is not None:
            return blocked
        cleaned = form.cleaned_data
        try:
            ptp = open_request(
                tenant_id=tenant_id,
                student_id=cleaned["student_id"],
                event_code=cleaned["event_code"],
                amount=cleaned["amount"],
                currency=cleaned["currency"],
                guardian_threshold=cleaned["guardian_threshold"],
            )
        except PermissionToPayError as exc:
            error = str(exc)
        else:
            request.session[_SESSION_KEY] = _serialize(ptp)
            request.session.modified = True
            # Swap to a fresh form so raw student_id from the submitted POST
            # does not echo back into the rendered HTML — only the hashed
            # in-flight summary should be visible after a successful open.
            form = OpenPermissionToPayForm()

    in_flight_blob = request.session.get(_SESSION_KEY)
    in_flight = _deserialize(in_flight_blob) if in_flight_blob else None
    return render(
        request,
        "finance/permission_to_pay.html",
        {
            "form": form,
            "approval_form": RecordGuardianApprovalForm(),
            "in_flight": in_flight,
            "error": error,
        },
    )


@login_required
@user_passes_test(_finance_roles_ok)
@require_school
@require_http_methods(["POST"])
def permission_to_pay_approve(request):
    """Record a guardian approval against the in-flight request."""
    blob = request.session.get(_SESSION_KEY)
    if not blob:
        return render(
            request,
            "finance/permission_to_pay.html",
            {
                "form": OpenPermissionToPayForm(),
                "approval_form": RecordGuardianApprovalForm(),
                "in_flight": None,
                "error": "no in-flight request",
            },
            status=400,
        )
    in_flight = _deserialize(blob)
    approval_form = RecordGuardianApprovalForm(request.POST)
    error = None
    if approval_form.is_valid():
        cleaned = approval_form.cleaned_data
        try:
            in_flight = record_guardian_approval(
                in_flight,
                guardian_id=cleaned["guardian_id"],
                approved_at_iso=cleaned["approved_at_iso"],
                method=cleaned["method"],
            )
        except PermissionToPayError as exc:
            error = str(exc)
        else:
            request.session[_SESSION_KEY] = _serialize(in_flight)
            request.session.modified = True
    return render(
        request,
        "finance/permission_to_pay.html",
        {
            "form": OpenPermissionToPayForm(),
            "approval_form": approval_form,
            "in_flight": in_flight,
            "error": error,
        },
    )


@login_required
@user_passes_test(_finance_roles_ok)
@require_school
@require_http_methods(["POST"])
def permission_to_pay_authorize(request):
    """Authorize payment for the in-flight request via the rail registry."""
    school = request.school
    tenant_id = str(school.pk) if school is not None else ""
    blob = request.session.get(_SESSION_KEY)
    if not blob:
        return render(
            request,
            "finance/permission_to_pay.html",
            {
                "form": OpenPermissionToPayForm(),
                "approval_form": RecordGuardianApprovalForm(),
                "in_flight": None,
                "error": "no in-flight request",
            },
            status=400,
        )
    in_flight = _deserialize(blob)
    # Ensure a fallback rail is registered so the call is safe in dev/test.
    if not payment_registry().rails():
        register_manual_fallback()
    error = None
    try:
        in_flight = authorize_payment(
            in_flight,
            tenant_id_raw_for_intent=tenant_id,
        )
    except PermissionToPayError as exc:
        error = str(exc)
    request.session[_SESSION_KEY] = _serialize(in_flight)
    request.session.modified = True
    return render(
        request,
        "finance/permission_to_pay.html",
        {
            "form": OpenPermissionToPayForm(),
            "approval_form": RecordGuardianApprovalForm(),
            "in_flight": in_flight,
            "error": error,
        },
    )
