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

from apps.analytics.services.tenant_overview_viz import (
    DEMO_TENANT_SLUGS,
    build_tenant_overview_bundle,
)


def _parse_iso_date(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value.strip()[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _session_school_id(request) -> str | None:
    if not hasattr(request, "session"):
        return None
    sid = (request.session.get("school_id") or "").strip()
    return sid or None


def _resolve_school_for_viz(request, tenant_slug: str):
    """
    Resolve school for live aggregates, or None for demo slugs.

    Returns (school, error_response). error_response is a JsonResponse when denied.
    """
    if tenant_slug in DEMO_TENANT_SLUGS:
        return None, None

    from apps.schools.models import School
    from apps.schools.tenant_switch_security import user_may_access_school_api

    host_school = getattr(request, "school", None)
    if host_school and getattr(host_school, "slug", None) == tenant_slug:
        school = host_school
    elif host_school and not tenant_slug:
        school = host_school
    else:
        school = School.objects.filter(slug=tenant_slug, is_active=True).first()

    if school is None:
        return None, JsonResponse(
            {"error": "tenant_not_found", "tenant": tenant_slug},
            status=404,
        )

    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None, JsonResponse({"error": "Authentication required"}, status=401)

    if not user_may_access_school_api(
        user, school, session_school_id=_session_school_id(request)
    ):
        return None, JsonResponse(
            {"error": "Forbidden", "tenant": tenant_slug},
            status=403,
        )

    return school, None


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

        school, deny = _resolve_school_for_viz(request, tenant_slug)
        if deny is not None:
            return deny

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
