"""v4.00.41 — Multi-campus group academic rollup (Wedge 22 extension).

Extends the v4.00.38 billing-only multicampus surface with grades +
attendance aggregates across the group's descendant schools. Built per
the same ``?wedge=22[&parent=<id>]`` filter contract.

Stable URL: ``/portal/super/wedges/multicampus-academics/?wedge=22[&parent=<id>]``

JSON: ``?format=json`` returns the rollup tree.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any

from django.contrib.admin.views.decorators import staff_member_required
from django.db.models import Avg, Q
from django.http import HttpRequest, JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from apps.siteconfig._wedge_registry import wedge

logger = logging.getLogger(__name__)


def _z() -> Decimal:
    return Decimal("0.00")


def _grade_aggregate(school_ids: list[int]) -> dict[str, Any]:
    if not school_ids:
        return {"evaluation_count": 0, "avg_final_score": None, "fail_count": 0, "pass_rate": None}
    try:
        from apps.evals.models import Evaluation
    except Exception as exc:  # noqa: BLE001
        logger.debug("multicampus academics: Evaluation unavailable: %s", exc)
        return {"error": "Evaluation_unavailable"}
    qs = Evaluation.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-multi-tenant-explicit-school-id-list
    total = qs.count()
    if not total:
        return {"evaluation_count": 0, "avg_final_score": None, "fail_count": 0, "pass_rate": None}
    avg = qs.aggregate(a=Avg("final_score")).get("a")
    fail = qs.filter(final_score__lt=50).count()  # magic-number-allow: rmc-pass-threshold-display
    return {
        "evaluation_count": total,
        "avg_final_score": str(round(float(avg or 0), 2)) if avg is not None else None,  # money-float-allow: average-score-not-money
        "fail_count": fail,
        "pass_rate": str(round(100.0 * (total - fail) / total, 1)) if total else None,
    }


def _attendance_aggregate(school_ids: list[int]) -> dict[str, Any]:
    if not school_ids:
        return {"record_count": 0, "present": 0, "absent": 0, "attendance_rate": None}
    try:
        from apps.academics.models import Attendance
    except Exception as exc:  # noqa: BLE001
        logger.debug("multicampus academics: Attendance unavailable: %s", exc)
        return {"error": "Attendance_unavailable"}
    qs = Attendance.objects.filter(school_id__in=school_ids)  # tenant-isolation-allow: group-rollup-multi-tenant-explicit-school-id-list
    total = qs.count()
    if not total:
        return {"record_count": 0, "present": 0, "absent": 0, "attendance_rate": None}
    present = qs.filter(Q(status__iexact="present") | Q(status__iexact="P")).count()
    absent = qs.filter(Q(status__iexact="absent") | Q(status__iexact="A")).count()
    rate = round(100.0 * present / total, 1) if total else None
    return {
        "record_count": total,
        "present": present,
        "absent": absent,
        "attendance_rate": str(rate) if rate is not None else None,
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
            "grade": _grade_aggregate([child.pk]),
            "attendance": _attendance_aggregate([child.pk]),
        })
    return {
        "parent": ({"id": parent.pk, "name": parent.name, "slug": getattr(parent, "slug", "")} if parent else None),
        "group_label": group_label,
        "children": children,
        "grade_rollup": _grade_aggregate(descendant_ids),
        "attendance_rollup": _attendance_aggregate(descendant_ids),
        "descendant_count": len(descendant_ids),
    }


@staff_member_required
@require_http_methods(["GET"])
def multicampus_academics(request: HttpRequest):
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
    return render(request, "super/wedges/surface_multicampus_academics.html", {
        "wedge": w,
        "tree": tree,
        "parent_id": parent_id,
    })
