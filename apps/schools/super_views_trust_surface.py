"""
Trust center, compliance overview, audit export, platform events, config redirect (BR-12 split from super_views).
"""

from __future__ import annotations

import csv
import json
from datetime import datetime, timedelta
from io import StringIO

from django.core.cache import cache
from django.db import DatabaseError
from django.http import HttpResponse
from django.shortcuts import redirect, render
from django.urls import NoReverseMatch, reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_http_methods

from apps.schools.control_plane import require_super_access_with_host
from apps.platform_runtime.operator_identity import (
    PLATFORM_SCOPE_AUDIT_EXPORT,
    PLATFORM_SCOPE_SECURITY_READ,
    PLATFORM_SCOPE_TENANT_READ,
    require_platform_scope,
)


@require_platform_scope(PLATFORM_SCOPE_SECURITY_READ)
def super_compliance_overview(request):
    """Phase 13: Control-plane compliance governance — policy pack, audit review, export risk."""

    def _safe_reverse(name: str) -> str:
        try:
            return reverse(name)
        except NoReverseMatch:
            return ""

    actions = [
        {
            "key": "audit_export",
            "title": "Audit export",
            "description": "Download audit-log evidence packs scoped by date, actor, and tenant.",
            "url": _safe_reverse("super:audit_export"),
            "icon": "bi-file-earmark-arrow-down",
            "category": "audit",
        },
        {
            "key": "platform_events",
            "title": "Platform event log",
            "description": "Search platform-wide event records — sensitive actions, actors, timestamps.",
            "url": _safe_reverse("super:platform_events"),
            "icon": "bi-search",
            "category": "audit",
        },
        {
            "key": "compliance_dashboard",
            "title": "Compliance dashboard",
            "description": "Overview of compliance posture across tenants, regions, and document status.",
            "url": _safe_reverse("compliance:dashboard"),
            "icon": "bi-clipboard-check",
            "category": "compliance",
        },
        {
            "key": "data_rights_queue",
            "title": "Data rights queue",
            "description": "Review and resolve subject access, export, and erasure requests.",
            "url": _safe_reverse("compliance:data_rights_queue"),
            "icon": "bi-person-lock",
            "category": "consent",
        },
        {
            "key": "data_portability_export",
            "title": "GDPR data portability",
            "description": "Initiate and track GDPR-compliant subject data exports.",
            "url": _safe_reverse("compliance:data_portability_export"),
            "icon": "bi-box-arrow-up-right",
            "category": "consent",
        },
        {
            "key": "erasure_request",
            "title": "GDPR erasure request",
            "description": "Open or follow up an erasure request through the four-eyes approval flow.",
            "url": _safe_reverse("compliance:erasure_request"),
            "icon": "bi-trash3",
            "category": "consent",
        },
        {
            "key": "compliance_exports",
            "title": "Compliance export jobs",
            "description": "Track scheduled compliance export jobs and download artifacts.",
            "url": _safe_reverse("siteconfig:compliance_exports"),
            "icon": "bi-archive",
            "category": "audit",
        },
        {
            "key": "policy_diff",
            "title": "Policy bundle diff",
            "description": "Compare policy bundles between schools and the canonical platform policy pack.",
            "url": _safe_reverse("super:policy_diff"),
            "icon": "bi-shield-check",
            "category": "policy",
        },
        {
            "key": "operator_policy",
            "title": "Operator policy",
            "description": "Configure operator-side policy: retention windows, evidence requirements.",
            "url": _safe_reverse("super:operator_policy"),
            "icon": "bi-sliders",
            "category": "policy",
        },
    ]

    actions = [a for a in actions if a["url"]]
    sot_register_url = "/docs/generated/external_dependencies_register.json"
    return render(
        request,
        "schools/super_compliance_overview.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "trust_center_url": reverse("super:trust_center"),
            "actions": actions,
            "sot_register_url": sot_register_url,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_SECURITY_READ)
def super_trust_center(request):
    """§10.5.4 Trust product: Security & Trust hub — Compliance, API Center, Sessions, Audit export (TRUST_PRODUCT_SURFACES.md)."""
    workflow_center_url = ""
    setup_studio_url = ""
    try:
        workflow_center_url = reverse("studio_os:workflow_center")
    except NoReverseMatch:
        pass
    try:
        setup_studio_url = reverse("siteconfig:guided_onboarding")
    except NoReverseMatch:
        pass
    sso_ctx = {"integrations_tracked": 0, "ok_last_7d": 0, "fail_last_7d": 0}
    week = timezone.now() - timedelta(days=7)
    try:
        from apps.accounts.models import FederationSsoHealth

        qs = FederationSsoHealth.objects.all()
        sso_ctx["integrations_tracked"] = qs.count()
        sso_ctx["ok_last_7d"] = qs.filter(last_success_at__gte=week).count()
        sso_ctx["fail_last_7d"] = qs.filter(last_failure_at__gte=week).count()
    except (DatabaseError, ImportError, ValueError, TypeError):
        pass
    platform_events_7d = 0
    try:
        from apps.platform_runtime.models import PlatformEventLog

        # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
        platform_events_7d = PlatformEventLog.objects.filter(
            created_at__gte=week
        ).count()
    except (DatabaseError, ImportError, ValueError, TypeError):
        pass
    district_enterprise_url = ""
    try:
        district_enterprise_url = reverse("super:district_enterprise")
    except NoReverseMatch:
        pass
    geography_url = ""
    try:
        geography_url = reverse("super:geography")
    except NoReverseMatch:
        pass
    from apps.platform_runtime.identity_graph_rollups import (
        compute_platform_identity_rollups,
    )
    from apps.schools.super_views_wedge import _beachhead_checklist

    return render(
        request,
        "schools/super_trust_center.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "compliance_url": reverse("super:compliance_overview"),
            "apicenter_url": reverse("apicenter:dashboard"),
            "workflow_center_url": workflow_center_url,
            "setup_studio_url": setup_studio_url,
            "sso_health": sso_ctx,
            "developer_api_url": "/developers/api-docs/",
            "public_trust_ferpa_url": "/trust-center/ferpa/",
            "platform_events_7d": platform_events_7d,
            "platform_events_url": reverse("super:platform_events"),
            "slo_dashboard_url": reverse("api_operational_slo_dashboard")
            + "?format=html&hours=168",
            "district_enterprise_url": district_enterprise_url,
            "geography_url": geography_url,
            "platform_rollups": compute_platform_identity_rollups(),
            "tenant_identity_graph_api_path": "/api/learning/identity-graph-summary/",
            "tenant_statutory_extract_api_path": "/api/learning/statutory-extract/",
            "sovereignty_pledge_url": "/docs/SOVEREIGNTY_PLEDGE.md",
            "beachhead_checklist": _beachhead_checklist(45),
            "beachhead_wedge_id": 45,
        },
    )


@require_platform_scope(PLATFORM_SCOPE_TENANT_READ)
def super_config_hub_redirect(request):
    """Legacy URL only. The single config surface is Configuration Control Center (siteconfig:console_domains_hub). No hub page; redirect."""
    return redirect("siteconfig:console_domains_hub", permanent=False)


@require_http_methods(["GET"])
@require_super_access_with_host
@require_platform_scope(PLATFORM_SCOPE_AUDIT_EXPORT)
def super_audit_export(request):
    """Export platform audit log (date range, CSV/JSON). Rate limit: one export per 60 seconds per user. TRUST_PRODUCT_SURFACES.md §3."""
    dashboard_url = reverse("super:dashboard")
    trust_center_url = reverse("super:trust_center")
    from_date_str = request.GET.get("from_date", "").strip()
    to_date_str = request.GET.get("to_date", "").strip()
    fmt = (request.GET.get("format") or "csv").strip().lower()
    if fmt not in ("csv", "json"):
        fmt = "csv"

    if not from_date_str or not to_date_str:
        return render(
            request,
            "schools/super_audit_export.html",
            {"dashboard_url": dashboard_url, "trust_center_url": trust_center_url},
        )

    from_date = parse_date(from_date_str)
    to_date = parse_date(to_date_str)
    if not from_date or not to_date:
        return render(
            request,
            "schools/super_audit_export.html",
            {
                "dashboard_url": dashboard_url,
                "trust_center_url": trust_center_url,
                "error": "Invalid date format.",
            },
        )
    if from_date > to_date:
        return render(
            request,
            "schools/super_audit_export.html",
            {
                "dashboard_url": dashboard_url,
                "trust_center_url": trust_center_url,
                "error": "From date must be before to date.",
            },
        )
    if (to_date - from_date).days > 365:
        return render(
            request,
            "schools/super_audit_export.html",
            {
                "dashboard_url": dashboard_url,
                "trust_center_url": trust_center_url,
                "error": "Date range must not exceed 365 days.",
            },
        )

    cache_key = f"super_audit_export_last:{getattr(request.user, 'id', 0)}"
    if cache.get(cache_key):
        return render(
            request,
            "schools/super_audit_export.html",
            {
                "dashboard_url": dashboard_url,
                "trust_center_url": trust_center_url,
                "error": "Rate limit: one export per 60 seconds.",
            },
        )
    cache.set(cache_key, True, timeout=60)

    from apps.compliance.models_audit import AuditLog

    start_naive = timezone.make_aware(datetime.combine(from_date, datetime.min.time()))
    end_naive = timezone.make_aware(datetime.combine(to_date, datetime.max.time()))
    qs = (
        AuditLog.objects.filter(timestamp__gte=start_naive, timestamp__lte=end_naive)
        .select_related("user")
        .order_by("timestamp")
    )
    rows = list(
        qs.values(
            "id",
            "timestamp",
            "action",
            "model_name",
            "object_id",
            "object_repr",
            "sensitivity",
            "app_label",
            "reason",
            "user_id",
            "ip_address",
        )
    )
    for r in rows:
        r["timestamp"] = (
            r["timestamp"].isoformat()
            if hasattr(r["timestamp"], "isoformat")
            else str(r["timestamp"])
        )

    if fmt == "json":
        response = HttpResponse(
            json.dumps(rows, indent=2, default=str),
            content_type="application/json",
        )
        response["Content-Disposition"] = 'attachment; filename="audit_export.json"'
        return response

    buf = StringIO()
    if rows:
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys(), extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    response = HttpResponse(buf.getvalue(), content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="audit_export.csv"'
    return response


@require_http_methods(["GET"])
@require_platform_scope(PLATFORM_SCOPE_SECURITY_READ)
def super_platform_events(request):
    """
    Append-only platform events (pack apply, rollback, catalog) for ops and trust surface.
    §0.3 Pillar 5 — complements Compliance audit export (admin actions).
    """
    from apps.platform_runtime.models import PlatformEventLog
    from apps.schools.control_plane_pagination import paginate_for_request

    page_obj = paginate_for_request(
        request,
        PlatformEventLog.objects.order_by("-created_at"),
        per_page=25,
    )
    events = list(
        page_obj.object_list.values(
            "id",
            "event_type",
            "tenant_id",
            "school_id",
            "idempotency_key",
            "created_at",
            "payload",
        )
    )
    for e in events:
        ts = e.get("created_at")
        e["created_at_display"] = ts.isoformat() if ts else ""
        pl = e.get("payload") or {}
        ps = str(pl) if pl else ""
        e["payload_preview"] = ps if len(ps) <= 240 else ps[:240] + "…"
    return render(
        request,
        "schools/super_platform_events.html",
        {
            "dashboard_url": reverse("super:dashboard"),
            "trust_center_url": reverse("super:trust_center"),
            "events": events,
            "page_obj": page_obj,
        },
    )
