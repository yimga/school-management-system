"""
§3.3 Metadata search and governance UI — stub API for catalog search.
Staff-only; returns entity catalog entries matching query.
"""
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_http_methods


def _staff_required(user):
    return getattr(user, "is_staff", False) or getattr(user, "is_superuser", False)


def _catalog_search(q: str, limit: int = 20, active_only: bool = True):
    """
    Shared catalog search logic for API and governance UI.
    When active_only=True (default), only returns entries with lifecycle_state=active.
    """
    if not (q or "").strip():
        return []
    from django.db.models import Q
    from apps.metadata.models import EntityCatalogEntry, ENTITY_CATALOG_LIFECYCLE_ACTIVE
    qs = EntityCatalogEntry.objects.filter(
        Q(code__icontains=q) | Q(name__icontains=q)
    )
    if active_only:
        qs = qs.filter(lifecycle_state=ENTITY_CATALOG_LIFECYCLE_ACTIVE)
    qs = qs.order_by("code")[:limit]
    return [
        {
            "code": e.code,
            "name": getattr(e, "name", "") or e.code,
            "owning_app": getattr(e, "owning_app", "") or "",
            "lifecycle_state": getattr(e, "lifecycle_state", "active") or "active",
            "model_label": getattr(e, "model_label", "") or "",
            "source_pack_id": getattr(e, "source_pack_id", "") or "",
            "source_pack_version": getattr(e, "source_pack_version", "") or "",
        }
        for e in qs
    ]


@login_required
@user_passes_test(_staff_required)
@require_http_methods(["GET"])
def metadata_governance_ui(request):
    """
    §3 Metadata governance UI: staff-only page to search catalog and see lineage/docs links.
    """
    q = (request.GET.get("q") or "").strip()[:100]
    try:
        limit = min(50, max(1, int(request.GET.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20
    results = _catalog_search(q, limit=limit) if q else []
    return render(request, "metadata/governance.html", {
        "query": q,
        "results": results,
        "search_api_path": "/api/internal/metadata/search/",
        "page_title": _("Metadata governance"),
        "page_subtitle": _("Search entity catalog by code or name. Use the API for programmatic access and lineage."),
        "action_url": reverse("studio_os:control"),
        "action_text": _("Back to Control"),
    })


@login_required
@user_passes_test(_staff_required)
@require_http_methods(["GET"])
def metadata_search_api(request):
    """
    GET ?q= — search metadata catalog (EntityCatalogEntry by code/name).
    Returns JSON: { "results": [ { "code", "name", "owning_app", "lifecycle_state", "model_label" }, ... ] }.
    By default only active lifecycle entries are returned; ?lifecycle=all includes draft/deprecated (staff).
    §3.3 metadata search stub; extend with governance filters and lineage.
    """
    q = (request.GET.get("q") or "").strip()[:100]
    try:
        limit = min(50, max(1, int(request.GET.get("limit", 20))))
    except (TypeError, ValueError):
        limit = 20
    active_only = request.GET.get("lifecycle") != "all"
    results = _catalog_search(q, limit=limit, active_only=active_only)
    return JsonResponse({"results": results})


@login_required
@user_passes_test(_staff_required)
@require_http_methods(["GET"])
def metadata_lineage_api(request):
    """
    GET ?object_type=entity&code=student | ?object_type=field&entity_code=student&field_name=admission_number
         | ?object_type=package&package_id=x | ?object_type=consumer&consumer_type=dashboard&consumer_code=principal_home
    §3.3 Unified lineage API: aggregates usage_registry + package lineage + blast radius.
    Returns JSON: object, downstream, downstream_summary, packages, blast_radius.
    """
    from apps.metadata.lineage_api import get_unified_lineage

    object_type = (request.GET.get("object_type") or "").strip().lower()
    code = (request.GET.get("code") or "").strip()
    entity_code = (request.GET.get("entity_code") or "").strip()
    field_name = (request.GET.get("field_name") or "").strip()
    package_id = (request.GET.get("package_id") or "").strip()
    consumer_type = (request.GET.get("consumer_type") or "").strip()
    consumer_code = (request.GET.get("consumer_code") or "").strip()
    try:
        limit = min(500, max(1, int(request.GET.get("limit", 100))))
    except (TypeError, ValueError):
        limit = 100

    payload = get_unified_lineage(
        object_type=object_type or "entity",
        code=code or None,
        entity_code=entity_code or None,
        field_name=field_name or None,
        package_id=package_id or None,
        consumer_type=consumer_type or None,
        consumer_code=consumer_code or None,
        limit=limit,
    )
    return JsonResponse(payload)


@login_required
@user_passes_test(_staff_required)
@require_http_methods(["GET"])
def metadata_lineage_graph_ui(request):
    """
    §3.3 Lineage graph UI: staff-only page to query "what uses this?" and see
    downstream consumers, blast radius, and packages. Renders form + result table + simple graph.
    """
    from apps.metadata.lineage_api import get_unified_lineage

    object_type = (request.GET.get("object_type") or "entity").strip().lower()
    code = (request.GET.get("code") or "").strip()
    entity_code = (request.GET.get("entity_code") or "").strip()
    field_name = (request.GET.get("field_name") or "").strip()
    package_id = (request.GET.get("package_id") or "").strip()
    consumer_type = (request.GET.get("consumer_type") or "").strip()
    consumer_code = (request.GET.get("consumer_code") or "").strip()
    has_query = bool(
        code or entity_code or field_name or package_id or consumer_type or consumer_code
    )
    payload = {}
    graph_consumers = []  # list of {"label", "x", "y"} for SVG layout (max 12)
    center_label = ""
    if has_query:
        payload = get_unified_lineage(
            object_type=object_type,
            code=code or None,
            entity_code=entity_code or None,
            field_name=field_name or None,
            package_id=package_id or None,
            consumer_type=consumer_type or None,
            consumer_code=consumer_code or None,
            limit=100,
        )
        obj = payload.get("object") or {}
        summary = payload.get("downstream_summary") or {}
        consumers = summary.get("consumers") or []
        center_label = (
            obj.get("entity_code")
            or obj.get("package_id")
            or (obj.get("consumer_type") or "") + ":" + (obj.get("consumer_code") or "")
            or "?"
        )[:12]
        import math
        n = min(12, len(consumers))
        for i in range(n):
            angle = 2 * math.pi * i / n - math.pi / 2  # start from top
            graph_consumers.append({
                "label": (consumers[i].get("consumer_code") or "?")[:14],
                "x": round(200 + 130 * math.cos(angle)),
                "y": round(200 + 130 * math.sin(angle)),
            })

    return render(
        request,
        "metadata/lineage_graph.html",
        {
            "object_type": object_type,
            "code": code,
            "entity_code": entity_code,
            "field_name": field_name,
            "package_id": package_id,
            "consumer_type": consumer_type,
            "consumer_code": consumer_code,
            "payload": payload,
            "has_query": has_query,
            "graph_consumers": graph_consumers,
            "center_label": center_label,
            "page_title": _("Lineage graph"),
            "page_subtitle": _("What uses this? Query by entity, field, package, or consumer. Downstream consumers and blast radius."),
            "action_url": reverse("studio_os:control"),
            "action_text": _("Back to Control"),
        },
    )
