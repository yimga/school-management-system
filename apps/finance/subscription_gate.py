"""
HTTP 402 gate for finance writes when platform billing is inactive (SFDP 1426).
"""

from __future__ import annotations

from django.http import HttpResponse, JsonResponse
from django.utils.deprecation import MiddlewareMixin

from apps.billing.models import BillingAccount

_FINANCE_WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

_EXEMPT_PATH_FRAGMENTS = (
    "/finance/payments/webhook/",
    "/payments/webhook/",
)

_OFFLINE_PROOF_FRAGMENTS = (
    "/upload-receipt/",
    "/api/offline/enqueue/",
)

_MARKETPLACE_BILLING_FRAGMENTS = (
    "/marketplace/",
    "/billing/webhook/",
    "/api/v1/marketplace/",
)


def billing_allows_finance_writes(school) -> bool:
    if school is None:
        return True
    try:
        account = getattr(school, "billing_account", None)
    except Exception:
        account = None
    if account is None:
        try:
            account = BillingAccount.objects.filter(school_id=school.pk).first()
        except Exception:
            return True
    if account is None:
        return True
    return account.status in (
        BillingAccount.Status.ACTIVE,
        BillingAccount.Status.TRIAL,
    )


def _offline_proof_exempt(request, school) -> bool:
    path = (request.path or "").lower()
    if not any(fragment in path for fragment in _OFFLINE_PROOF_FRAGMENTS):
        return False
    if "/api/offline/enqueue/" in path:
        action = (
            (request.POST.get("action_type") or request.GET.get("action_type") or "")
            .strip()
            .lower()
        )
        if action not in {"payment.proof_upload", "payment_receipt", "payment_proof"}:
            return False
    from apps.finance.models import TenantPaymentPolicy

    policy = TenantPaymentPolicy.objects.filter(school_id=school.pk).first()
    return bool(policy and policy.allow_manual_offline_proof)


def finance_subscription_blocked_response(request) -> HttpResponse:
    if request.path.startswith("/api/") or "application/json" in (
        request.headers.get("Accept") or ""
    ):
        return JsonResponse(
            {
                "error": "subscription_inactive",
                "detail": "Platform subscription is inactive. Finance writes are paused.",
            },
            status=402,
        )
    return HttpResponse(
        "<h1>402 Payment Required</h1>"
        "<p>Platform subscription is inactive. Contact your school administrator.</p>",
        status=402,
        content_type="text/html",
    )


class FinanceSubscriptionGateMiddleware(MiddlewareMixin):
    """Block finance mutating routes when BillingAccount is past due / suspended / canceled."""

    def process_request(self, request):
        if request.method not in _FINANCE_WRITE_METHODS:
            return None
        path = request.path or ""
        if not any(token in path for token in ("/finance/", "/fees/")):
            return None
        if any(fragment in path for fragment in _EXEMPT_PATH_FRAGMENTS):
            return None
        if any(fragment in path for fragment in _MARKETPLACE_BILLING_FRAGMENTS):
            return None
        school = getattr(request, "school", None)
        if school is None:
            return None
        if billing_allows_finance_writes(school):
            return None
        if _offline_proof_exempt(request, school):
            return None
        return finance_subscription_blocked_response(request)
