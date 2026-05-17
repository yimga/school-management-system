"""
v2.94 — control-plane (manager.runmycampus.com) cross-school integrations
rollup. Closes the v2.89 honest-gap #10.

The per-tenant `/integrations/rollup/` view in views.py answers "what does
this one school have connected, across all its campuses?". This view
answers the platform-owner question: "across every active school, who has
which integrations connected?". Used by the operations team to spot
schools that haven't activated their stack, audit which providers are most
popular across the platform, and triage when a connector outage is
reported (which tenants are even using it?).

Mounted on manager.runmycampus.com via config.manager_urls.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from apps.schools.control_plane import require_control_plane_access


@require_control_plane_access
def manager_integrations_rollup(request: HttpRequest) -> HttpResponse:
    """Cross-school integrations rollup. Read-only."""
    from apps.integrations_marketplace.connector_registry import (
        CATEGORY_LABELS, list_connectors,
    )
    from apps.schools.models import School
    from apps.siteconfig.models_platform_catalog import ServiceIntegration

    connector_filter = (request.GET.get("connector") or "").strip().lower()

    # Control-plane operator surface — by design walks every active tenant to give ops a platform-wide view.
    rows_qs = ServiceIntegration.objects.filter(is_active=True).exclude(  # tenant-isolation-allow: control-plane operator surface, platform-wide view by design
        connector_slug=""
    )
    if connector_filter:
        rows_qs = rows_qs.filter(connector_slug__iexact=connector_filter)
    rows_qs = rows_qs.select_related("school", "campus").order_by(
        "school__name", "connector_slug"
    )

    # Build the matrix in Python — fewer queries, cleaner template.
    # Shape: { school_pk: { "school": School, "by_connector": { slug: [row,...] } } }
    matrix: dict[int, dict] = {}
    # tenant-isolation-allow: platform operator wants every active tenant in scope.
    for s in School.objects.filter(is_active=True).order_by("name"):
        matrix[s.pk] = {"school": s, "by_connector": {}}
    for row in rows_qs.iterator():
        school_pk = getattr(row.school, "pk", None)
        if school_pk not in matrix:
            # School inactive but row active — surface as orphan column.
            matrix[school_pk] = {"school": row.school, "by_connector": {}}
        matrix[school_pk]["by_connector"].setdefault(row.connector_slug, []).append(row)

    # Per-connector totals (how many schools have this one connected at all).
    totals_by_connector: dict[str, int] = {}
    for school_entry in matrix.values():
        for slug in school_entry["by_connector"]:
            totals_by_connector[slug] = totals_by_connector.get(slug, 0) + 1

    all_connectors = list_connectors()
    if connector_filter:
        all_connectors = [c for c in all_connectors if c.slug == connector_filter]

    ctx = {
        "schools": [matrix[k] for k in matrix],
        "connectors": [
            {
                "slug": c.slug,
                "label": c.label,
                "category_label": CATEGORY_LABELS.get(c.category, c.category),
                "schools_connected": totals_by_connector.get(c.slug, 0),
            }
            for c in all_connectors
        ],
        "connector_filter": connector_filter,
        "available_filters": sorted({c.slug for c in list_connectors()}),
        "total_schools": len(matrix),
        "total_rows": rows_qs.count(),
    }
    return render(request, "integrations_marketplace/manager_rollup.html", ctx)


@require_control_plane_access
def manager_bulk_prestage(request):
    """v3.4 — district-level provisioning: pre-create ServiceIntegration rows
    in a `pending OAuth` state for many schools at once. Each school admin
    then completes the OAuth dance at their leisure from the hub.

    POST fields:
      connector_slug  — required, must be a known OAuth connector slug
      school_ids      — required, comma- or whitespace-separated list of pks

    Idempotent: existing active rows are skipped. Returns a JSON summary.
    """
    from django.http import JsonResponse
    from django.shortcuts import render

    if request.method != "POST":
        # GET renders the form.
        from apps.integrations_marketplace.connector_registry import (
            list_oauth_connectors,
        )
        from apps.schools.models import School

        return render(
            request,
            "integrations_marketplace/manager_bulk_prestage.html",
            {
                "connectors": [c.to_dict() for c in list_oauth_connectors()],
                # tenant-isolation-allow: control-plane operator surface walks
                # every active tenant by design.
                "schools": list(School.objects.filter(is_active=True).order_by("name")),
            },
        )

    connector_slug = (request.POST.get("connector_slug") or "").strip().lower()
    raw_ids = (request.POST.get("school_ids") or "").replace(",", " ").split()
    try:
        school_ids = [int(s) for s in raw_ids if s.strip().isdigit()]
    except ValueError:
        school_ids = []
    if not connector_slug or not school_ids:
        return JsonResponse(
            {"ok": False, "error": "missing connector_slug or school_ids"},
            status=400,
        )

    from apps.integrations_marketplace.connector_registry import (
        AUTH_KIND_OAUTH2, get_connector,
    )
    connector = get_connector(connector_slug)
    if connector is None or connector.auth_kind != AUTH_KIND_OAUTH2:
        return JsonResponse(
            {"ok": False, "error": f"connector {connector_slug!r} is not OAuth"},
            status=400,
        )
    if connector.deprecated:
        return JsonResponse(
            {"ok": False, "error": f"connector {connector_slug!r} is deprecated"},
            status=400,
        )

    from apps.schools.models import School
    from apps.siteconfig.models_platform_catalog import ServiceIntegration

    created, skipped = [], []
    # tenant-isolation-allow: operator-driven bulk provisioning across tenants.
    for school in School.objects.filter(pk__in=school_ids, is_active=True):
        existing = ServiceIntegration.objects.filter(
            school=school, campus__isnull=True,
            connector_slug__iexact=connector.slug,
        ).first()
        if existing is not None:
            skipped.append({"school_id": school.pk, "row_id": existing.pk,
                            "reason": "row_already_exists"})
            continue
        row = ServiceIntegration.objects.create(
            school=school,
            campus=None,
            service_name=connector.slug,
            service_type=ServiceIntegration.ServiceType.OAUTH,
            connector_slug=connector.slug,
            config={"pending_oauth": True, "prestaged_at": __import__("time").time()},
            enabled_scopes=list(connector.default_scopes),
            is_active=False,
        )
        created.append({"school_id": school.pk, "row_id": row.pk})
    return JsonResponse({
        "ok": True,
        "connector": connector.slug,
        "created": created,
        "skipped": skipped,
        "total_requested": len(school_ids),
    })


__all__ = ["manager_bulk_prestage", "manager_integrations_rollup"]
