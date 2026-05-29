"""v4.00.42 — Multi-campus group operational rollup (Wedge 22 extension).

Extends the v4.00.38 billing + v4.00.41 academics surfaces with three new
group-level aggregates the SuperAdmin operator needs for cross-campus
oversight:

  * **Events** — per-campus + rolled-up SchoolEvent counts split by status
    (draft / published / completed / canceled) + total fundraising goal.
  * **Fees collection** — per-campus + rolled-up Payment count and amount
    sum (a fees-collection rate proxy: ``payment_total / invoice_total``).
  * **Staff headcount** — per-campus + rolled-up TeacherProfile counts
    (active vs total) plus per-campus department coverage.

Stable URL:
  ``/portal/super/wedges/multicampus-extension/?wedge=22[&parent=<id>]``

JSON: ``?format=json`` returns the rollup tree.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Count, Sum
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.siteconfig._wedge_registry import wedge

logger = logging.getLogger(__name__)


def _z() -> Decimal:
    return Decimal("0.00")


def _events_aggregate(school_ids: list[int]) -> dict[str, Any]:
    if not school_ids:
        return {"event_count": 0, "draft": 0, "published": 0, "completed": 0, "canceled": 0, "fundraising_goal_total": str(_z())}
    try:
        from apps.school_events.models import SchoolEvent
    except Exception as exc:  # noqa: BLE001
        logger.debug("multicampus extension: SchoolEvent unavailable: %s", exc)
        return {"error": "SchoolEvent_unavailable"}
    qs = SchoolEvent.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-events-by-explicit-school-id-list
    total = qs.count()
    if not total:
        return {"event_count": 0, "draft": 0, "published": 0, "completed": 0, "canceled": 0, "fundraising_goal_total": str(_z())}
    by_status = qs.values("status").annotate(n=Count("id"))
    counts = {row["status"]: row["n"] for row in by_status}
    fundraising = qs.aggregate(s=Sum("fundraising_goal")).get("s") or _z()
    return {
        "event_count": total,
        "draft": int(counts.get("draft", 0)),
        "published": int(counts.get("published", 0)),
        "completed": int(counts.get("completed", 0)),
        "canceled": int(counts.get("canceled", 0)),
        "fundraising_goal_total": str(fundraising),
    }


def _fees_aggregate(school_ids: list[int]) -> dict[str, Any]:
    if not school_ids:
        return {"invoice_total": str(_z()), "payment_total": str(_z()), "payment_count": 0, "collection_rate": None}
    try:
        from apps.finance.models import Invoice, Payment
    except Exception as exc:  # noqa: BLE001
        logger.debug("multicampus extension: finance models unavailable: %s", exc)
        return {"error": "finance_models_unavailable"}
    inv_qs = Invoice.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-fees-by-explicit-school-id-list
    pay_qs = Payment.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-fees-by-explicit-school-id-list
    inv_total = inv_qs.aggregate(s=Sum("total_amount")).get("s") or _z()
    pay_total = pay_qs.aggregate(s=Sum("amount")).get("s") or _z()
    rate: str | None = None
    if inv_total and inv_total > 0:
        rate = str(round(float(pay_total) / float(inv_total) * 100.0, 1))  # money-float-allow: ratio-not-money
    return {
        "invoice_total": str(inv_total),
        "payment_total": str(pay_total),
        "payment_count": pay_qs.count(),
        "collection_rate": rate,
    }


def _discipline_aggregate(school_ids: list[int]) -> dict[str, Any]:
    """v4.00.46 — Discipline Incident rollup."""
    if not school_ids:
        return {"incident_count": 0, "open": 0, "resolved": 0, "high_severity": 0}
    try:
        from apps.academics.models import Incident
    except Exception as exc:  # noqa: BLE001
        logger.debug("multicampus extension: Incident unavailable: %s", exc)
        return {"error": "Incident_unavailable"}
    qs = Incident.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-discipline-by-explicit-school-id-list
    total = qs.count()
    if not total:
        return {"incident_count": 0, "open": 0, "resolved": 0, "high_severity": 0}
    open_n = qs.filter(status__in=["OPEN", "REFERRED"]).count()
    resolved_n = qs.filter(status="RESOLVED").count()
    high_sev = qs.filter(severity="HIGH").count()
    return {
        "incident_count": total,
        "open": open_n,
        "resolved": resolved_n,
        "high_severity": high_sev,
    }


def _transport_aggregate(school_ids: list[int]) -> dict[str, Any]:
    """v4.00.46 — Transport Route + Stop rollup."""
    if not school_ids:
        return {"route_count": 0, "active_routes": 0, "stop_count": 0}
    try:
        from apps.schoolops.models import Route, Stop
    except Exception as exc:  # noqa: BLE001
        logger.debug("multicampus extension: Route/Stop unavailable: %s", exc)
        return {"error": "Route_unavailable"}
    routes = Route.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-transport-routes-by-explicit-school-id-list
    total = routes.count()
    active = routes.filter(is_active=True).count()
    stops = Stop.objects.filter(route__school_id__in=school_ids).count()  # tenant-isolation-allow: group-rollup-transport-stops-by-explicit-school-id-list
    return {
        "route_count": total,
        "active_routes": active,
        "stop_count": stops,
    }


def _staff_aggregate(school_ids: list[int]) -> dict[str, Any]:
    if not school_ids:
        return {"teacher_total": 0, "teacher_active": 0, "teacher_inactive": 0, "department_count": 0}
    try:
        from apps.people.models import TeacherProfile
    except Exception as exc:  # noqa: BLE001
        logger.debug("multicampus extension: TeacherProfile unavailable: %s", exc)
        return {"error": "TeacherProfile_unavailable"}
    qs = TeacherProfile.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-staff-by-explicit-school-id-list
    total = qs.count()
    active = qs.filter(is_active=True).count()
    dept_count = qs.exclude(department__isnull=True).values("department_id").distinct().count()
    return {
        "teacher_total": total,
        "teacher_active": active,
        "teacher_inactive": total - active,
        "department_count": dept_count,
    }


def _build_tree(parent_id: int | None) -> dict[str, Any]:
    try:
        from apps.schools.models import School
    except Exception as exc:  # noqa: BLE001
        return {"error": f"school_model_unavailable: {exc}"}

    base_qs = School.objects.all()  # tenant-isolation-allow: group-rollup-platform-scope
    parent = base_qs.filter(pk=parent_id).first() if parent_id else None
    if parent is not None:
        children_qs = base_qs.filter(parent_school_id=parent.pk).order_by("name")
        group_label = parent.name
    else:
        children_qs = base_qs.filter(parent_school__isnull=True).order_by("name")
        group_label = "All multi-campus groups"

    children: list[dict[str, Any]] = []
    descendant_ids: list[int] = []
    if parent is not None:
        descendant_ids.append(parent.pk)
    for child in children_qs[:500]:
        descendant_ids.append(child.pk)
        children.append({
            "id": child.pk,
            "slug": getattr(child, "slug", ""),
            "name": getattr(child, "name", ""),
            "events": _events_aggregate([child.pk]),
            "fees": _fees_aggregate([child.pk]),
            "staff": _staff_aggregate([child.pk]),
            "discipline": _discipline_aggregate([child.pk]),
            "transport": _transport_aggregate([child.pk]),
        })
    return {
        "parent": ({"id": parent.pk, "name": parent.name, "slug": getattr(parent, "slug", "")} if parent else None),
        "group_label": group_label,
        "children": children,
        "events_rollup": _events_aggregate(descendant_ids),
        "fees_rollup": _fees_aggregate(descendant_ids),
        "staff_rollup": _staff_aggregate(descendant_ids),
        "discipline_rollup": _discipline_aggregate(descendant_ids),
        "transport_rollup": _transport_aggregate(descendant_ids),
        "descendant_count": len(descendant_ids),
    }


@staff_member_required
@require_http_methods(["GET"])
def multicampus_extension(request: HttpRequest):
    wedge_id_raw = (request.GET.get("wedge") or "").strip()
    w = None
    if wedge_id_raw:
        try:
            w = wedge(int(wedge_id_raw))
        except (ValueError, TypeError):
            w = None
    try:
        parent_id = int(request.GET.get("parent") or 0) or None
    except (ValueError, TypeError):
        parent_id = None

    tree = _build_tree(parent_id)
    if (request.GET.get("format") or "").lower() == "json":
        return JsonResponse({
            "success": True,
            "wedge": w["id"] if w else None,
            "parent_id": parent_id,
            "tree": tree,
        })
    return render(request, "super/wedges/surface_multicampus_extension.html", {
        "wedge": w,
        "tree": tree,
        "parent_id": parent_id,
    })
