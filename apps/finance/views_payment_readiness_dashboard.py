"""
Tenant-scoped payment readiness + gateway health snapshot (staff operator).

Requires ``request.school`` from tenant middleware so snapshots stay school-scoped.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.admin.views.decorators import staff_member_required
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.billing.regional_payment_readiness import compute_payment_readiness

from .payment_gateway_health import (
    GatewayHealthStatus,
    availability_map_from_rows,
    build_gateway_health_rows,
    latest_snapshots_per_rail,
    next_operator_action,
    record_gateway_health_snapshots,
)
from .payment_fallback_engine import select_effective_rail
from .regional_payment_profiles import get_normalized_regional_profile
from .views_common import _active_profile


def _payment_readiness_status_strip(health_rows: list[dict]) -> list[dict]:
    items: list[dict] = []
    for row in health_rows:
        st = str(row.get("status") or "").lower()
        rc = row.get("rail_code") or "?"
        msg = (row.get("message") or "")[:200]
        if st == GatewayHealthStatus.EXTERNAL_REQUIRED:
            items.append(
                {
                    "label": _("External PSP · %(rail)s") % {"rail": rc},
                    "tone": "warning",
                    "title": msg,
                }
            )
        elif st == GatewayHealthStatus.MISSING_CREDENTIALS:
            items.append(
                {
                    "label": _("Missing credentials · %(rail)s") % {"rail": rc},
                    "tone": "danger",
                    "title": msg,
                }
            )
        elif st == GatewayHealthStatus.DEGRADED:
            items.append(
                {
                    "label": _("Degraded · %(rail)s") % {"rail": rc},
                    "tone": "warning",
                    "title": msg,
                }
            )
    return items


def _payment_readiness_primary_cta(
    readiness: dict, health_rows: list[dict]
) -> tuple[str, str]:
    setup_url = reverse("finance:payment_readiness_setup")
    if readiness.get("status") == "READY":
        return setup_url, _("Review rails, backup & manual fallback")
    if any(
        r.get("status") == GatewayHealthStatus.MISSING_CREDENTIALS for r in health_rows
    ):
        return setup_url, _("Resolve missing credentials")
    if any(
        r.get("status") == GatewayHealthStatus.EXTERNAL_REQUIRED for r in health_rows
    ):
        return setup_url, _("Complete PSP setup or enable manual fallback")
    return setup_url, _("Complete payment setup")


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

    strip_items = _payment_readiness_status_strip(health_rows)
    primary_cta_url, primary_cta_label = _payment_readiness_primary_cta(
        readiness, health_rows
    )
    readiness_display_label = {
        "READY": _("Ready"),
        "FALLBACK_ONLY": _("Fallback only"),
        "MISSING_SETUP": _("Needs setup"),
    }.get(str(readiness.get("status")), str(readiness.get("status") or "—"))

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
            "os_strip_items": strip_items,
            "primary_cta_url": primary_cta_url,
            "primary_cta_label": primary_cta_label,
            "readiness_display_label": readiness_display_label,
        },
    )
