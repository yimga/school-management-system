"""Operator dashboard for holding-company multi-currency rollups (B4)."""
from __future__ import annotations

import logging
from typing import Any

from django.contrib import messages
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_http_methods

from apps.billing.holding_rollup import (
    iter_holding_parent_schools,
    materialize_holding_currency_rollups,
)
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_BILLING_READ,
    require_platform_scope,
)
from apps.schools.control_plane import require_super_access_with_host
from apps.schools.models import School

logger = logging.getLogger(__name__)


def _rollup_rows_for_parent(parent) -> list[dict[str, Any]]:
    from apps.siteconfig.models_platform_catalog import HoldingCurrencyRollup

    rows = []
    for rollup in HoldingCurrencyRollup.objects.filter(parent_school=parent).order_by(
        "currency_code"
    ):
        rows.append(
            {
                "currency_code": rollup.currency_code,
                "total_amount": str(rollup.total_amount),
                "source_school_count": rollup.source_school_count,
                "as_of": rollup.as_of.isoformat() if rollup.as_of else None,
            }
        )
    return rows


def _build_holdings_payload() -> list[dict[str, Any]]:
    holdings: list[dict[str, Any]] = []
    for parent in iter_holding_parent_schools():
        child_count = parent.get_child_schools().count()
        holdings.append(
            {
                "id": str(parent.pk),
                "name": parent.name,
                "slug": getattr(parent, "slug", ""),
                "child_count": child_count,
                "currency_buckets": _rollup_rows_for_parent(parent),
            }
        )
    return holdings


@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_BILLING_READ)
@require_http_methods(["GET", "POST"])
def holding_currency_rollup_dashboard(request: HttpRequest) -> HttpResponse:
    """# rbac-allow: super-staff-holding-currency-rollup-dashboard"""
    if request.method == "POST":
        parent_id = (request.POST.get("parent_id") or "").strip()
        if parent_id:
            parent = get_object_or_404(School, pk=parent_id, is_active=True)
            materialize_holding_currency_rollups(parent)
            messages.success(
                request,
                _("Refreshed currency buckets for %(name)s.") % {"name": parent.name},
            )
        else:
            refreshed = 0
            for parent in iter_holding_parent_schools():
                materialize_holding_currency_rollups(parent)
                refreshed += 1
            messages.success(
                request,
                _("Refreshed holding currency rollups for %(count)s group(s).")
                % {"count": refreshed},
            )
        return redirect("super:holding_currency_rollup_dashboard")

    holdings = _build_holdings_payload()
    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({"holdings": holdings})

    total_buckets = sum(len(h["currency_buckets"]) for h in holdings)
    return render(
        request,
        "schools/holding_currency_rollup_dashboard.html",
        {
            "holdings": holdings,
            "holding_count": len(holdings),
            "total_buckets": total_buckets,
            "billing_dashboard_url": reverse("super:billing_dashboard"),
            "multicampus_billing_url": reverse("super:wedge_surface_multicampus_billing"),
        },
    )
