"""
Tenant-scoped payment readiness + gateway health snapshot (staff operator).

Requires ``request.school`` from tenant middleware so snapshots stay school-scoped.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render

from apps.billing.regional_payment_readiness import compute_payment_readiness

from .payment_gateway_health import (
    availability_map_from_rows,
    build_gateway_health_rows,
    latest_snapshots_per_rail,
    next_operator_action,
    record_gateway_health_snapshots,
)
from .payment_fallback_engine import select_effective_rail
from .regional_payment_profiles import get_normalized_regional_profile
from .views_common import _active_profile


@staff_member_required(login_url=settings.LOGIN_URL)
def payment_readiness_dashboard(request: HttpRequest):
    profile = _active_profile(request)
    if not profile:
        return HttpResponseForbidden("No compliance profile configured.")

    school = getattr(request, "school", None)
    if not school:
        return HttpResponseForbidden("Open from a school (tenant) workspace.")

    readiness = compute_payment_readiness(school, profile)
    catalog = get_normalized_regional_profile(
        profile.country_code if profile else None
    )
    health_rows = build_gateway_health_rows(school, profile)
    record_gateway_health_snapshots(school, health_rows)
    latest_checks = latest_snapshots_per_rail(school)
    next_action = next_operator_action(health_rows, catalog)
    effective = select_effective_rail(
        profile.country_code if profile else None,
        availability_map_from_rows(health_rows),
    )

    status_badge_class = {
        "READY": "success",
        "FALLBACK_ONLY": "warning",
        "MISSING_SETUP": "danger",
    }.get(readiness["status"], "secondary")

    return render(
        request,
        "finance/payment_readiness_dashboard.html",
        {
            "profile": profile,
            "school": school,
            "readiness": readiness,
            "catalog": catalog or {},
            "health_rows": health_rows,
            "latest_checks": latest_checks,
            "next_action": next_action,
            "effective_rail": effective,
            "status_badge_class": status_badge_class,
        },
    )
