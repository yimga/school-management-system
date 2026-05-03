"""
Operator-facing payment readiness checklist (global corridors + campus policy).
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render

from apps.billing.regional_payment_readiness import compute_payment_readiness

from .views_common import _active_profile


@staff_member_required(login_url=settings.LOGIN_URL)
def payment_readiness_setup(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    school = getattr(request, "school", None)
    readiness = compute_payment_readiness(school, profile)

    status_badge_class = {
        "READY": "success",
        "FALLBACK_ONLY": "warning",
        "MISSING_SETUP": "danger",
    }.get(readiness["status"], "secondary")

    return render(
        request,
        "finance/payment_readiness_setup.html",
        {
            "profile": profile,
            "readiness": readiness,
            "status_badge_class": status_badge_class,
        },
    )
