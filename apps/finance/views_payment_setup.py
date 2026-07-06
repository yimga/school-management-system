"""
Operator-facing payment readiness checklist (global corridors + campus policy).
"""

from __future__ import annotations

from django.conf import settings
from apps.accounts.decorators import require_permission
from apps.accounts.step_up import require_step_up
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render

from apps.billing.regional_payment_readiness import compute_payment_readiness

from .views_common import _active_profile


@require_permission("finance.manage")
@require_step_up()
def payment_readiness_setup(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    school = getattr(request, "school", None)
    readiness = compute_payment_readiness(school, profile)

    from apps.finance.models import TenantPaymentPolicy
    from apps.finance.payment_orchestration import build_simple_payment_flow

    tenant_payment_policy = None
    simple_payment_flow = build_simple_payment_flow(None)
    if school is not None:
        tenant_payment_policy = TenantPaymentPolicy.objects.filter(school=school).select_related(
            "region_profile__primary_rail",
            "region_profile__backup_rail",
        ).first()
        if tenant_payment_policy:
            simple_payment_flow = build_simple_payment_flow(tenant_payment_policy)

    status_badge_class = {
        "READY": "success",
        "FALLBACK_ONLY": "warning",
        "MISSING_SETUP": "danger",
    }.get(readiness["status"], "secondary")

    from apps.finance.payment_lane2_status import build_lane2_corridor_rows, stripe_connect_summary
    from django.urls import reverse

    lane2_corridors = build_lane2_corridor_rows(school=school)
    stripe_connect = stripe_connect_summary(school=school)
    stripe_connect_url = reverse("siteconfig:billing_stripe_connect")

    return render(
        request,
        "finance/payment_readiness_setup.html",
        {
            "profile": profile,
            "readiness": readiness,
            "status_badge_class": status_badge_class,
            "tenant_payment_policy": tenant_payment_policy,
            "simple_payment_flow": simple_payment_flow,
            "lane2_corridors": lane2_corridors,
            "stripe_connect": stripe_connect,
            "stripe_connect_url": stripe_connect_url,
        },
    )
