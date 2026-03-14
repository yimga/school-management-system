"""
Section 11: Super-admin API and HTML views for benchmark intelligence (11.3) and customer success (11.4).
All views require Super Admin access (use require_super_access in urlconf).
"""
from django.db import DatabaseError
from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_GET

from apps.schools.models import School

CUSTOMER_SUCCESS_VIEW_SOFT_FAILURES = (
    AttributeError,
    DatabaseError,
    TypeError,
    ValueError,
)


def _bounded_limit(raw_value, default: int, maximum: int) -> int:
    try:
        parsed = int(raw_value)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, maximum))


# ---------- 11.3 Benchmark intelligence ----------


@require_GET
def api_benchmark_cohorts(request):
    """GET: List benchmark cohorts for dropdowns and peer selection."""
    from .models import BenchmarkCohort
    cohorts = list(
        BenchmarkCohort.objects.filter(is_active=True).values(
            "id", "name", "country_code", "region_code", "size_band", "institution_type"
        )
    )
    return JsonResponse({"cohorts": cohorts})


@require_GET
def api_benchmark_peer_metrics(request):
    """GET: Peer benchmark metrics (avg maturity/health) for a school. Query: school_id."""
    school_id = request.GET.get("school_id", "").strip()
    if not school_id:
        return JsonResponse({"error": "school_id required"}, status=400)
    school = get_object_or_404(School, pk=school_id)
    from .services import get_peer_benchmark_metrics
    maturity_avg = get_peer_benchmark_metrics(school, "maturity")
    health_avg = get_peer_benchmark_metrics(school, "health")
    return JsonResponse({
        "school_id": str(school.id),
        "peer_avg_maturity": maturity_avg,
        "peer_avg_health": health_avg,
    })


@require_GET
def api_maturity_scores(request):
    """GET: Latest maturity scores for a school or all. Query: school_id (optional)."""
    from .models import TenantMaturityScore
    school_id = request.GET.get("school_id", "").strip()
    if school_id:
        school = get_object_or_404(School, pk=school_id)
        seen = set()
        out = []
        for s in TenantMaturityScore.objects.filter(school=school).order_by("-computed_at"):
            if s.dimension not in seen:
                seen.add(s.dimension)
                out.append({
                    "dimension": s.dimension,
                    "score": str(s.score),
                    "computed_at": s.computed_at.isoformat(),
                    "payload": s.payload,
                })
        return JsonResponse({"school_id": str(school.id), "scores": out})
    # All schools: latest score per school (overall or first dimension)
    from django.db.models import Subquery, OuterRef
    latest = TenantMaturityScore.objects.filter(school_id=OuterRef("pk")).order_by("-computed_at")
    schools = School.objects.filter(is_active=True).annotate(
        latest_maturity_at=Subquery(latest.values("computed_at")[:1]),
        latest_maturity_score=Subquery(latest.values("score")[:1]),
    ).values("id", "name", "slug", "latest_maturity_at", "latest_maturity_score")
    rows = []
    for s in schools:
        rows.append({
            "school_id": str(s["id"]),
            "name": s["name"],
            "slug": s["slug"],
            "latest_maturity_at": s["latest_maturity_at"].isoformat() if s.get("latest_maturity_at") else None,
            "latest_maturity_score": str(s["latest_maturity_score"]) if s.get("latest_maturity_score") is not None else None,
        })
    return JsonResponse({"schools": rows})


@require_GET
def api_risk_alerts(request):
    """GET: Tenant risk alerts (amber/red). Query: school_id (optional), acknowledged=0|1."""
    from .models import TenantRiskAlert
    school_id = request.GET.get("school_id", "").strip()
    acknowledged = request.GET.get("acknowledged", "").strip()
    qs = TenantRiskAlert.objects.select_related("school").order_by("-created_at")
    if school_id:
        qs = qs.filter(school_id=school_id)
    if acknowledged == "1":
        qs = qs.filter(acknowledged_at__isnull=False)
    elif acknowledged == "0":
        qs = qs.filter(acknowledged_at__isnull=True)
    alerts = []
    for a in qs[:100]:
        alerts.append({
            "id": a.pk,
            "school_id": str(a.school_id),
            "school_name": a.school.name,
            "severity": a.severity,
            "reason": a.reason,
            "suggested_action": a.suggested_action,
            "created_at": a.created_at.isoformat(),
            "acknowledged_at": a.acknowledged_at.isoformat() if a.acknowledged_at else None,
        })
    return JsonResponse({"alerts": alerts})


@require_GET
def api_intervention_suggestions(request):
    """GET: Intervention suggestions for a school or all. Query: school_id (optional), dismissed=0|1."""
    from .models import TenantInterventionSuggestion
    school_id = request.GET.get("school_id", "").strip()
    dismissed = request.GET.get("dismissed", "").strip()
    qs = TenantInterventionSuggestion.objects.select_related("school").order_by("priority", "-created_at")
    if school_id:
        qs = qs.filter(school_id=school_id)
    if dismissed == "1":
        qs = qs.filter(dismissed_at__isnull=False)
    elif dismissed == "0":
        qs = qs.filter(dismissed_at__isnull=True)
    suggestions = []
    for s in qs[:100]:
        suggestions.append({
            "id": s.pk,
            "school_id": str(s.school_id),
            "school_name": s.school.name,
            "category": s.category,
            "title": s.title,
            "description": s.description,
            "priority": s.priority,
            "created_at": s.created_at.isoformat(),
            "dismissed_at": s.dismissed_at.isoformat() if s.dismissed_at else None,
        })
    return JsonResponse({"suggestions": suggestions})


# ---------- 11.4 Customer success ----------


@require_GET
def api_tenant_health(request):
    """GET: Tenant health scores. Query: school_id (optional). Computes and stores if missing for today."""
    school_id = request.GET.get("school_id", "").strip()
    from .services import ensure_health_score_record
    from .models import TenantHealthScore

    if school_id:
        school = get_object_or_404(School, pk=school_id)
        ensure_health_score_record(school)
        scores = list(
            TenantHealthScore.objects.filter(school=school).order_by("-computed_at")[:7].values(
                "score", "dimensions", "computed_at"
            )
        )
        for s in scores:
            s["computed_at"] = s["computed_at"].isoformat()
            s["score"] = str(s["score"])
        return JsonResponse({"school_id": str(school.id), "health_scores": scores})

    # All tenants: page through active schools instead of silently truncating at 200.
    limit = _bounded_limit(request.GET.get("limit"), 200, 1000)
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
    except (TypeError, ValueError):
        offset = 0
    schools = School.objects.filter(is_active=True).order_by("name")
    total_count = schools.count()
    out = []
    for school in schools[offset:offset + limit]:
        ensure_health_score_record(school)
        latest = TenantHealthScore.objects.filter(school=school).order_by("-computed_at").first()
        if latest:
            out.append({
                "school_id": str(school.id),
                "name": school.name,
                "slug": school.slug,
                "score": str(latest.score),
                "dimensions": latest.dimensions,
                "computed_at": latest.computed_at.isoformat(),
            })
    return JsonResponse(
        {
            "tenants": out,
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": offset + limit < total_count,
        }
    )


@require_GET
def api_workflow_failures(request):
    """GET: Recent workflow failure events. Query: school_id (optional), limit (default 50)."""
    from .models import WorkflowFailureEvent
    school_id = request.GET.get("school_id", "").strip()
    limit = min(100, max(1, int(request.GET.get("limit", 50))))
    qs = WorkflowFailureEvent.objects.select_related("school").order_by("-created_at")[:limit]
    if school_id:
        qs = qs.filter(school_id=school_id)
    events = []
    for e in qs:
        events.append({
            "id": e.pk,
            "school_id": str(e.school_id),
            "school_name": e.school.name,
            "workflow_name": e.workflow_name,
            "workflow_run_id": e.workflow_run_id,
            "error_summary": e.error_summary,
            "created_at": e.created_at.isoformat(),
        })
    return JsonResponse({"events": events})


@require_GET
def api_admin_inactivity_alerts(request):
    """GET: Admin inactivity alerts. Query: school_id (optional)."""
    from .models import AdminInactivityAlert
    school_id = request.GET.get("school_id", "").strip()
    qs = AdminInactivityAlert.objects.select_related("school").order_by("-created_at")[:100]
    if school_id:
        qs = qs.filter(school_id=school_id)
    alerts = []
    for a in qs:
        alerts.append({
            "id": a.pk,
            "school_id": str(a.school_id),
            "school_name": a.school.name,
            "last_admin_activity": a.last_admin_activity.isoformat(),
            "threshold_days": a.threshold_days,
            "created_at": a.created_at.isoformat(),
            "notified_at": a.notified_at.isoformat() if a.notified_at else None,
            "ticket_created": a.ticket_created,
        })
    return JsonResponse({"alerts": alerts})


# ---------- HTML dashboard (optional) ----------


@require_GET
def customer_success_dashboard(request):
    """Super dashboard: benchmark, health, risk alerts, interventions, workflow failures in one view."""
    from .models import TenantRiskAlert, TenantInterventionSuggestion, WorkflowFailureEvent, TenantHealthScore
    from .services import ensure_health_score_record

    dashboard_limit = _bounded_limit(request.GET.get("limit"), 50, 200)
    active_schools = list(School.objects.filter(is_active=True).order_by("name")[:dashboard_limit])
    for school in active_schools:
        try:
            ensure_health_score_record(school)
        except CUSTOMER_SUCCESS_VIEW_SOFT_FAILURES:
            pass

    alerts = TenantRiskAlert.objects.filter(acknowledged_at__isnull=True).select_related("school").order_by("-created_at")[:20]
    suggestions = TenantInterventionSuggestion.objects.filter(dismissed_at__isnull=True).select_related("school").order_by("priority", "-created_at")[:20]
    failures = WorkflowFailureEvent.objects.select_related("school").order_by("-created_at")[:20]
    health_scores = TenantHealthScore.objects.filter(school__in=active_schools).order_by("school", "-computed_at")
    # Latest per school
    seen_schools = set()
    health_list = []
    for h in health_scores:
        if h.school_id not in seen_schools:
            seen_schools.add(h.school_id)
            health_list.append(h)

    return render(
        request,
        "customersuccess/super_dashboard.html",
        {
            "alerts": alerts,
            "suggestions": suggestions,
            "workflow_failures": failures,
            "health_scores": health_list,
            "dashboard_limit": dashboard_limit,
            "dashboard_url": "/super/",
        },
    )
