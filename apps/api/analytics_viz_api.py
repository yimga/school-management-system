"""JSON API for unified analytics viz (TenantOverview React bundle)."""

from __future__ import annotations

import json
from datetime import datetime

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest, JsonResponse
from django.urls import reverse
from django.utils.decorators import method_decorator
from django.views import View
from django.views.decorators.http import require_http_methods

from apps.analytics.services.tenant_overview_viz import build_tenant_overview_bundle


def _parse_iso_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _resolve_school(request, tenant_slug: str):
    school = getattr(request, "school", None)
    if school and getattr(school, "slug", None) == tenant_slug:
        return school
    if school and not tenant_slug:
        return school
    try:
        from apps.schools.models import School

        return School.objects.filter(slug=tenant_slug, is_active=True).first()
    except Exception:
        return school


@method_decorator(login_required, name="dispatch")
@method_decorator(require_http_methods(["GET"]), name="dispatch")
class AnalyticsVizOverviewAPIView(View):
    """GET /api/internal/analytics-viz/overview/?tenant=<slug>&from=&to=&compare=1"""

    def get(self, request):
        tenant_slug = (request.GET.get("tenant") or "").strip()
        if not tenant_slug:
            school = getattr(request, "school", None)
            tenant_slug = getattr(school, "slug", "") or ""
        if not tenant_slug:
            return HttpResponseBadRequest(
                json.dumps({"error": "tenant query parameter required"}),
                content_type="application/json",
            )

        from_date = _parse_iso_date(request.GET.get("from"))
        to_date = _parse_iso_date(request.GET.get("to"))
        compare = request.GET.get("compare") in ("1", "true", "yes")

        school = _resolve_school(request, tenant_slug)
        try:
            bundle = build_tenant_overview_bundle(
                tenant_id=tenant_slug,
                school=school,
                from_date=from_date,
                to_date=to_date,
                compare=compare,
            )
        except Exception as exc:
            return JsonResponse(
                {"error": "overview_unavailable", "detail": str(exc)[:200]},
                status=503,
            )

        return JsonResponse(
            {
                "bundle": bundle,
                "api": reverse("api:api-analytics-viz-overview"),
            }
        )
