"""
Governed report builder UI + JSON preview/export API + decision intelligence surfaces.
"""

from __future__ import annotations

import csv
import io
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from apps.reports.export_integrity import attach_export_integrity_headers

from .governed_query.audit import log_governed_export_event
from .governed_query.executor import (
    GovernedQueryError,
    execute_governed_query,
    serialize_catalog_for_ui,
)
from .insight_registry import (
    SURFACE_ENGAGEMENT,
    SURFACE_FOUNDER,
    SURFACE_REVENUE,
    SURFACE_RISK,
    SURFACE_SCHOOL_HEALTH,
    build_global_rollup_insights,
    build_insights_for_school,
    filter_insights_by_surface,
)


def _GovernedSavedReport():
    """Deferred import avoids circular ``apps.analytics.models`` loading during URLconf import."""
    from .models import GovernedSavedReport

    return GovernedSavedReport


_ALLOWED_DEFINITION_KEYS = frozenset(
    {"dataset_id", "fields", "filters", "group_by", "aggregate", "limit"}
)


def _can_reports(user) -> bool:
    return bool(
        getattr(user, "is_superuser", False)
        or user.has_feature_permission("reports.manage")
        or user.has_feature_permission("data.access")
    )


def _sanitize_definition(raw: dict | None) -> dict:
    out: dict = {}
    if not isinstance(raw, dict):
        return out
    for k in _ALLOWED_DEFINITION_KEYS:
        if k not in raw:
            continue
        if k == "limit":
            try:
                out[k] = min(max(int(raw[k]), 1), 5000)
            except (TypeError, ValueError):
                out[k] = 200
        else:
            out[k] = raw[k]
    return out


def _school_or_none(request):
    return getattr(request, "school", None)


@login_required
@require_GET
def governed_report_builder(request):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    sid = str(school.pk) if school else None
    catalog = serialize_catalog_for_ui(request.user)
    _run_magic = 884_422_001
    return render(
        request,
        "analytics/governed_report_builder.html",
        {
            "governed_catalog_json": json.dumps(catalog),
            "school_id": sid,
            "preview_url": reverse("analytics:governed_query_preview"),
            "export_csv_url": reverse("analytics:governed_query_export_csv"),
            "export_json_url": reverse("analytics:governed_query_export_json"),
            "saved_list_url": reverse("analytics:governed_saved_reports_list"),
            "saved_save_url": reverse("analytics:governed_saved_report_save"),
            "saved_run_url_magic": reverse(
                "analytics:governed_saved_report_run",
                kwargs={"report_id": _run_magic},
            ),
            "saved_run_magic": str(_run_magic),
        },
    )


def _execute_from_payload(request, payload: dict):
    school = _school_or_none(request)
    sid = str(school.pk) if school else None
    return execute_governed_query(
        user=request.user,
        school_id=sid,
        dataset_id=payload.get("dataset_id") or "",
        fields=payload.get("fields"),
        filters=payload.get("filters"),
        group_by=payload.get("group_by"),
        aggregate=payload.get("aggregate"),
        limit=min(int(payload.get("limit") or 200), 5000),
    )


@login_required
@require_POST
def governed_query_preview(request):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    try:
        rows, meta = _execute_from_payload(request, payload)
    except GovernedQueryError as e:
        return JsonResponse({"error": str(e)}, status=400)

    return JsonResponse({"rows": rows, "meta": meta})


@login_required
@require_POST
def governed_query_export_csv(request):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    sid = str(school.pk) if school else None
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return HttpResponse("invalid json", status=400)

    try:
        rows, meta = _execute_from_payload(request, payload)
    except GovernedQueryError as e:
        return HttpResponse(str(e), status=400)

    if not rows:
        buf = "\ufeff".encode("utf-8")
        resp = HttpResponse(buf, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = (
            'attachment; filename="governed_export_empty.csv"'
        )
        return resp

    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    raw = ("\ufeff" + buf.getvalue()).encode("utf-8")

    log_governed_export_event(
        user_id=getattr(request.user, "pk", None),
        school_id=sid,
        dataset_id=payload.get("dataset_id") or "",
        row_count=len(rows),
        export_format="csv",
        aggregate=bool(meta.get("aggregated")),
    )

    resp = HttpResponse(raw, content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = (
        f'attachment; filename="governed_{payload.get("dataset_id") or "export"}.csv"'
    )
    try:
        attach_export_integrity_headers(
            resp,
            content=raw,
            export_key=f"governed:{payload.get('dataset_id') or 'export'}",
            school_id=sid or "global",
            secret=settings.SECRET_KEY,
        )
    except Exception:
        pass
    return resp


@login_required
@require_POST
def governed_query_export_json(request):
    """Same rows as preview; audited as an export (API-friendly JSON body)."""
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    sid = str(school.pk) if school else None
    try:
        payload = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    try:
        rows, meta = _execute_from_payload(request, payload)
    except GovernedQueryError as e:
        return JsonResponse({"error": str(e)}, status=400)

    log_governed_export_event(
        user_id=getattr(request.user, "pk", None),
        school_id=sid,
        dataset_id=payload.get("dataset_id") or "",
        row_count=len(rows),
        export_format="json",
        aggregate=bool(meta.get("aggregated")),
    )

    return JsonResponse({"rows": rows, "meta": meta})


@login_required
@require_GET
def governed_saved_reports_list(request):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    if not school:
        return JsonResponse({"saved": [], "error": "no tenant context"}, status=400)
    qs = _GovernedSavedReport().objects.filter(school=school).values(
        "id", "name", "updated_at"
    )[:200]
    data = []
    for row in qs:
        data.append(
            {
                "id": row["id"],
                "name": row["name"],
                "updated_at": row["updated_at"].isoformat()
                if row["updated_at"]
                else None,
            }
        )
    return JsonResponse({"saved": data})


@login_required
@require_POST
def governed_saved_report_save(request):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    if not school:
        return JsonResponse({"error": "no tenant context"}, status=400)
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    name = (body.get("name") or "").strip()[:200]
    if not name:
        return JsonResponse({"error": "name required"}, status=400)

    definition = _sanitize_definition(body.get("definition"))
    if not definition.get("dataset_id"):
        return JsonResponse({"error": "definition.dataset_id required"}, status=400)

    obj = _GovernedSavedReport().objects.create(
        school=school,
        created_by=request.user,
        name=name,
        definition=definition,
    )
    return JsonResponse({"id": obj.pk, "name": obj.name})


@login_required
@require_POST
def governed_saved_report_run(request, report_id: int):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    if not school:
        return JsonResponse({"error": "no tenant context"}, status=400)

    report = _GovernedSavedReport().objects.filter(
        pk=report_id, school_id=school.pk
    ).first()
    if not report:
        return JsonResponse({"error": "not found"}, status=404)

    payload = dict(report.definition)
    payload.setdefault("limit", 500)
    try:
        rows, meta = _execute_from_payload(request, payload)
    except GovernedQueryError as e:
        return JsonResponse({"error": str(e)}, status=400)

    log_governed_export_event(
        user_id=getattr(request.user, "pk", None),
        school_id=str(school.pk),
        dataset_id=payload.get("dataset_id") or "",
        row_count=len(rows),
        export_format="saved_report",
        aggregate=bool(meta.get("aggregated")),
    )

    return JsonResponse(
        {"rows": rows, "meta": meta, "saved_report_id": report.pk, "name": report.name}
    )


@login_required
@require_GET
def decision_intelligence_dashboard(request):
    """Overview: all school insights + optional founder rollup strip."""
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    sid = str(school.pk) if school else None
    insights = build_insights_for_school(sid, user=request.user) if sid else []
    rollup = []
    if getattr(request.user, "is_superuser", False):
        rollup = build_global_rollup_insights()
    return render(
        request,
        "analytics/decision_intelligence_dashboard.html",
        {
            "insights": insights,
            "global_rollups": rollup,
            "school_id": sid,
            "surface_title": "Overview",
            "surface_key": "overview",
            "show_founder_nav": getattr(request.user, "is_superuser", False),
            "founder_only": False,
        },
    )


def _render_decision_surface(request, surface: str, title: str):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    sid = str(school.pk) if school else None
    all_i = build_insights_for_school(sid, user=request.user) if sid else []
    insights = filter_insights_by_surface(all_i, surface)
    return render(
        request,
        "analytics/decision_surface_dashboard.html",
        {
            "insights": insights,
            "global_rollups": [],
            "school_id": sid,
            "surface_title": title,
            "surface_key": surface,
            "show_founder_nav": getattr(request.user, "is_superuser", False),
            "founder_only": False,
        },
    )



@login_required
@require_GET
def decision_school_health_dashboard(request):
    return _render_decision_surface(request, SURFACE_SCHOOL_HEALTH, "School health")


@login_required
@require_GET
def decision_revenue_dashboard(request):
    return _render_decision_surface(request, SURFACE_REVENUE, "Revenue")


@login_required
@require_GET
def decision_engagement_dashboard(request):
    return _render_decision_surface(request, SURFACE_ENGAGEMENT, "Engagement")


@login_required
@require_GET
def decision_risk_dashboard(request):
    return _render_decision_surface(request, SURFACE_RISK, "Risk")


@login_required
@require_GET
def decision_founder_dashboard(request):
    if not getattr(request.user, "is_superuser", False):
        return HttpResponseForbidden("Founder dashboard requires superuser.")
    insights = build_global_rollup_insights()
    # Only founder-surface cards (defensive if registry grows)
    insights = [i for i in insights if SURFACE_FOUNDER in i.get("surfaces", [])]
    return render(
        request,
        "analytics/decision_surface_dashboard.html",
        {
            "insights": insights,
            "global_rollups": [],
            "school_id": None,
            "surface_title": "Founder / global rollup",
            "surface_key": SURFACE_FOUNDER,
            "show_founder_nav": True,
            "founder_only": True,
        },
    )
