"""
Governed report builder UI + JSON preview/export API + decision intelligence surfaces.
"""

from __future__ import annotations

import csv
import io
import json

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse, HttpResponseForbidden, JsonResponse
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
from .event_analytics_rollups import build_event_analytics_bundle
from .governed_intent import (
    ALLOWED_INTENT_IDS,
    insight_for_intent,
    match_governed_intent,
    rebuild_definition_for_intent,
)
from .insight_registry import (
    SURFACE_ENGAGEMENT,
    SURFACE_FOUNDER,
    SURFACE_REVENUE,
    SURFACE_RISK,
    SURFACE_SCHOOL_HEALTH,
    build_global_rollup_insights,
    build_insights_for_school,
    ensure_primary_action_url_inplace,
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


def _audit_analytics_governed_event(
    *,
    user,
    school_id: str | None,
    action: str,
    model_name: str,
    object_id: str,
    reason: str,
    new_values: dict | None = None,
) -> None:
    try:
        from apps.compliance.models_audit import AuditLog

        AuditLog.objects.create(
            user=user if getattr(user, "is_authenticated", False) else None,
            action=action,
            model_name=model_name[:100],
            object_id=str(object_id)[:200],
            object_repr=reason[:500],
            sensitivity=AuditLog.Sensitivity.MEDIUM,
            app_label="analytics",
            new_values=new_values or {},
            reason=reason[:255],
        )
    except Exception:
        pass


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

    from apps.compliance.models_audit import AuditLog

    _audit_analytics_governed_event(
        user=request.user,
        school_id=sid,
        action=AuditLog.Action.EXPORT,
        model_name="GovernedQueryCsvExport",
        object_id=payload.get("dataset_id") or "csv",
        reason="governed_query_export_csv",
        new_values={
            "dataset_id": payload.get("dataset_id"),
            "row_count": len(rows),
            "aggregated": bool(meta.get("aggregated")),
        },
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
def governed_saved_report_detail(request, report_id: int):
    """HTML detail for a tenant-bound saved governed report (definition summary + run/export links)."""
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    if not school:
        return HttpResponseForbidden("Tenant context required.")
    report = (
        _GovernedSavedReport()
        .objects.filter(pk=report_id, school_id=school.pk)
        .first()
    )
    if not report:
        raise Http404("Saved report not found.")
    return render(
        request,
        "analytics/governed_saved_report_detail.html",
        {
            "report": report,
            "definition_json": json.dumps(report.definition, indent=2, sort_keys=True),
            "run_url": reverse(
                "analytics:governed_saved_report_run", kwargs={"report_id": report.pk}
            ),
            "builder_url": reverse("analytics:governed_report_builder"),
            "saved_list_url": reverse("analytics:governed_saved_reports_list"),
        },
    )


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

    from apps.compliance.models_audit import AuditLog

    _audit_analytics_governed_event(
        user=request.user,
        school_id=str(school.pk),
        action=AuditLog.Action.CREATE,
        model_name="GovernedSavedReport",
        object_id=str(obj.pk),
        reason="governed_saved_report_create",
        new_values={
            "name": obj.name,
            "dataset_id": definition.get("dataset_id"),
            "school_id": str(school.pk),
        },
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


@login_required
@require_GET
def event_analytics_dashboard(request):
    """Event-scale analytics — ORM rollups + governed snapshot cards (no raw SQL)."""
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    if not school:
        return HttpResponseForbidden("Tenant context required.")
    sid = str(school.pk)
    bundle = build_event_analytics_bundle(user=request.user, school_id=sid, days=14)
    if not bundle.get("ok"):
        return HttpResponseForbidden(bundle.get("error") or "bundle denied")
    return render(
        request,
        "analytics/event_analytics_dashboard.html",
        {
            "school_id": sid,
            "bundle_json": json.dumps(bundle, indent=2, default=str),
            "builder_url": reverse("analytics:governed_report_builder"),
            "intent_url": reverse("analytics:governed_intent_assistant"),
        },
    )


@login_required
@require_GET
def event_analytics_bundle_api(request):
    """JSON bundle for charts (same data as dashboard; CSRF-free GET for same-origin XHR)."""
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    if not school:
        return JsonResponse({"ok": False, "error": "tenant_required"}, status=400)
    bundle = build_event_analytics_bundle(user=request.user, school_id=str(school.pk), days=14)
    return JsonResponse(bundle, safe=False)


@login_required
@require_GET
def governed_intent_assistant(request):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    return render(
        request,
        "analytics/governed_intent_assistant.html",
        {
            "school_id": str(school.pk) if school else None,
            "preview_url": reverse("analytics:governed_intent_preview"),
            "execute_url": reverse("analytics:governed_intent_execute"),
            "builder_url": reverse("analytics:governed_report_builder"),
            "events_url": reverse("analytics:event_analytics_dashboard"),
        },
    )


@login_required
@require_POST
def governed_intent_preview(request):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    text = (body.get("text") or "").strip()
    m = match_governed_intent(text)
    if not m.supported:
        return JsonResponse(
            {"supported": False, "reason": m.reason or "not_supported"},
            status=200,
        )
    return JsonResponse(
        {
            "supported": True,
            "intent_id": m.intent_id,
            "label": m.label,
            "governed_preview": m.governed_definition,
            "insight": m.insight,
        }
    )


@login_required
@require_POST
def governed_intent_execute(request):
    if not _can_reports(request.user):
        return HttpResponseForbidden("Reports permission required.")
    school = _school_or_none(request)
    if not school:
        return JsonResponse({"error": "no tenant context"}, status=400)
    try:
        body = json.loads(request.body.decode("utf-8") or "{}")
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)
    intent_id = (body.get("intent_id") or "").strip()
    if body.get("confirm") is not True:
        return JsonResponse({"error": "confirm_required"}, status=400)
    if intent_id not in ALLOWED_INTENT_IDS:
        return JsonResponse({"error": "unknown_intent"}, status=400)
    definition = rebuild_definition_for_intent(intent_id)
    if not definition:
        return JsonResponse({"error": "unknown_intent"}, status=400)

    insight = insight_for_intent(intent_id)
    if insight:
        ensure_primary_action_url_inplace(insight)

    try:
        rows, meta = execute_governed_query(
            user=request.user,
            school_id=str(school.pk),
            dataset_id=definition["dataset_id"],
            fields=definition.get("fields"),
            filters=definition.get("filters"),
            group_by=definition.get("group_by"),
            aggregate=definition.get("aggregate"),
            limit=min(int(definition.get("limit") or 200), 5000),
        )
    except GovernedQueryError as e:
        return JsonResponse({"error": str(e)}, status=400)

    log_governed_export_event(
        user_id=getattr(request.user, "pk", None),
        school_id=str(school.pk),
        dataset_id=definition.get("dataset_id") or "",
        row_count=len(rows),
        export_format="governed_intent",
        aggregate=bool(meta.get("aggregated")),
    )

    return JsonResponse(
        {
            "rows": rows,
            "meta": meta,
            "intent_id": intent_id,
            "insight": insight,
        }
    )
