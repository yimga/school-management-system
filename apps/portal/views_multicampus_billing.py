"""v4.00.38 — Multi-campus group billing rollup (Wedge 22).

The control plane carries a ``School.parent_school`` self-FK so school
groups can be represented as a tree. This view rolls up Invoice +
Payment aggregates across the descendants of a parent school so the
group operator can see central balance / collections in one place.

Stable URL: ``/portal/super/wedges/multicampus-billing/?wedge=22[&parent=<school_id>]``

The ``?wedge=22`` parameter is *the canonical filter contract* for
Wedge 22; this view consumes it explicitly (in addition to ``parent=``)
so it shows up in the wedge index's "with-filter" deep link.

JSON: ``?format=json`` returns the rollup tree + totals.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Sum
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.siteconfig._wedge_registry import wedge

logger = logging.getLogger(__name__)


def _z() -> Decimal:
    return Decimal("0.00")


def _aggregate_for_schools(school_ids: list[int]) -> dict[str, Any]:
    """Sum invoice + payment numbers for the given school PKs."""
    if not school_ids:
        return {
            "invoice_count": 0,
            "invoice_total": str(_z()),
            "balance_total": str(_z()),
            "payment_count": 0,
            "payment_total": str(_z()),
        }
    try:
        from apps.finance.models import Invoice, Payment
    except Exception as exc:  # noqa: BLE001
        logger.warning("multicampus billing: finance models unavailable: %s", exc)
        return {"error": "finance_models_unavailable"}
    inv_qs = Invoice.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-multi-tenant-by-explicit-school-id-list
    pay_qs = Payment.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-multi-tenant-by-explicit-school-id-list
    invoice_total = inv_qs.aggregate(s=Sum("total_amount")).get("s") or _z()
    balance_total = inv_qs.aggregate(s=Sum("balance_amount")).get("s") or _z()
    payment_total = pay_qs.aggregate(s=Sum("amount")).get("s") or _z()
    return {
        "invoice_count": inv_qs.count(),
        "invoice_total": str(invoice_total),
        "balance_total": str(balance_total),
        "payment_count": pay_qs.count(),
        "payment_total": str(payment_total),
    }


def _build_group_tree(parent_id: int | None) -> dict[str, Any]:
    """Return the parent + children + rollup aggregates."""
    try:
        from apps.schools.models import School
    except Exception as exc:  # noqa: BLE001
        return {"error": f"school_model_unavailable: {exc}"}

    base_qs = School.objects.all()  # tenant-isolation-allow: group-rollup-platform-scope
    parent = None
    if parent_id:
        parent = base_qs.filter(pk=parent_id).first()
    parent_pk = parent.pk if parent else None

    if parent is not None:
        children_qs = base_qs.filter(parent_school_id=parent_pk).order_by("name")
        group_label = parent.name
    else:
        # Default: list every distinct parent_school in the platform.
        children_qs = base_qs.filter(parent_school__isnull=True).order_by("name")
        group_label = "All multi-campus groups"

    children: list[dict[str, Any]] = []
    descendant_ids: list[int] = []
    if parent is not None:
        descendant_ids.append(parent.pk)
    for child in children_qs[:500]:
        descendant_ids.append(child.pk)
        agg = _aggregate_for_schools([child.pk])
        children.append({
            "id": child.pk,
            "slug": getattr(child, "slug", ""),
            "name": getattr(child, "name", ""),
            "subdomain": getattr(child, "subdomain", ""),
            "agg": agg,
        })
    rollup = _aggregate_for_schools(descendant_ids)

    return {
        "parent": (
            {"id": parent.pk, "name": parent.name, "slug": getattr(parent, "slug", "")}
            if parent is not None
            else None
        ),
        "group_label": group_label,
        "children": children,
        "rollup": rollup,
        "descendant_count": len(descendant_ids),
    }


@staff_member_required
@require_http_methods(["GET"])
def multicampus_billing(request: HttpRequest):
    """Rollup page for Wedge 22. Honors ``?wedge=22`` + ``?parent=<id>``."""
    wedge_id_raw = (request.GET.get("wedge") or "").strip()
    w = None
    if wedge_id_raw:
        try:
            w = wedge(int(wedge_id_raw))
        except (ValueError, TypeError):
            w = None
    parent_id: int | None
    try:
        parent_id = int(request.GET.get("parent") or 0) or None
    except (ValueError, TypeError):
        parent_id = None

    tree = _build_group_tree(parent_id)

    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "wedge": w["id"] if w else None,
            "parent_id": parent_id,
            "tree": tree,
        })
    return render(request, "super/wedges/surface_multicampus_billing.html", {
        "wedge": w,
        "tree": tree,
        "parent_id": parent_id,
    })
