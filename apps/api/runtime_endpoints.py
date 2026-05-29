"""Canonical /api/v1/runtime/* endpoints (v4.00.0).

These are the slow-changing tenant config payloads the Cloudflare Worker
fronts with SWR. The Django side stamps ``Surrogate-Key`` headers via
``services.edge_cache.stamp_response`` so the Worker can selectively purge
each bucket when ``RuntimeDefaults`` / ``SiteSettings`` change.

Endpoints (mount under ``api/v1/runtime/``):

  GET /calendar              — academic calendar snapshot
  GET /grading-matrix        — grading scale + cutoffs
  GET /defaults              — RuntimeDefaults bag
  GET /site-settings         — SiteSettings public snapshot
  GET /feature-flags         — resolved flags for the current tenant

The payloads are intentionally minimal — anything that needs auth or that
varies per user does NOT belong here.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe

from services.edge_cache import stamp_response

try:
    from drf_spectacular.utils import OpenApiResponse, extend_schema
except ImportError:  # drf_spectacular is in requirements; defensive only
    def extend_schema(*args, **kwargs):  # type: ignore[misc]
        def _decorator(fn):
            return fn
        return _decorator
    OpenApiResponse = None  # type: ignore[assignment]

_RUNTIME_TAG = "runtime"
_RUNTIME_DESCRIPTION = (
    "Edge-cached tenant config snapshots fronted by Cloudflare Workers (v4.00.0). "
    "Honor Surrogate-Key + Cache-Control headers on the response."
)


def _resolve_tenant_slug(request: HttpRequest) -> str:
    school = getattr(request, "school", None)
    if school is not None:
        slug = getattr(school, "slug", None) or getattr(school, "subdomain", None)
        if slug:
            return str(slug)
    return request.get_host().split(":", 1)[0]


def _resolve_viewport(request: HttpRequest) -> str:
    return (request.META.get("HTTP_X_RMC_VIEWPORT", "") or "A").strip().upper()[:1] or "A"


def _runtime_response(request: HttpRequest, view: str, payload: dict[str, Any]) -> JsonResponse:
    response = JsonResponse(payload, json_dumps_params={"separators": (",", ":")})
    stamp_response(
        response,
        tenant=_resolve_tenant_slug(request),
        view=view,
        viewport=_resolve_viewport(request),
    )
    return response


@extend_schema(tags=[_RUNTIME_TAG], summary="Academic calendar snapshot", description=_RUNTIME_DESCRIPTION)
@require_safe
@cache_control(public=True, max_age=15, s_maxage=900)
def school_calendar_runtime(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/runtime/calendar — academic calendar bundle.

    Pulls term boundaries + holiday list from ``apps.academics`` when available;
    falls back to an empty calendar when models are not yet wired.
    """
    payload: dict[str, Any] = {"terms": [], "holidays": [], "generated_at": None}
    try:
        from datetime import datetime, timezone

        from apps.academics.models import AcademicTerm  # type: ignore[attr-defined]
    except ImportError:
        return _runtime_response(request, "school_calendar", payload)
    school = getattr(request, "school", None)
    qs = AcademicTerm.objects.all()
    if school is not None:
        qs = qs.filter(school=school)
    payload["terms"] = [
        {
            "id": str(t.id),
            "name": getattr(t, "name", ""),
            "starts_on": getattr(t, "starts_on", None) and t.starts_on.isoformat(),
            "ends_on": getattr(t, "ends_on", None) and t.ends_on.isoformat(),
        }
        for t in qs.order_by("starts_on")[:64]
    ]
    payload["generated_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return _runtime_response(request, "school_calendar", payload)


@extend_schema(tags=[_RUNTIME_TAG], summary="Grading scale + cutoffs", description=_RUNTIME_DESCRIPTION)
@require_safe
@cache_control(public=True, max_age=15, s_maxage=900)
def grading_matrix_runtime(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/runtime/grading-matrix — grading scale + cutoffs."""
    payload: dict[str, Any] = {"scale": [], "passing_threshold": None}
    school = getattr(request, "school", None)
    if school is None:
        return _runtime_response(request, "grading_matrix", payload)
    settings_dict = getattr(school, "settings", None) or {}
    payload["scale"] = settings_dict.get("grading_scale") or []
    payload["passing_threshold"] = settings_dict.get("grading_passing_threshold")
    return _runtime_response(request, "grading_matrix", payload)


@extend_schema(tags=[_RUNTIME_TAG], summary="RuntimeDefaults projection", description=_RUNTIME_DESCRIPTION)
@require_safe
@cache_control(public=True, max_age=15, s_maxage=900)
def runtime_defaults_snapshot(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/runtime/defaults — RuntimeDefaults projection."""
    payload: dict[str, Any] = {"defaults": {}}
    try:
        from apps.platform_runtime.models import RuntimeDefaults  # type: ignore[attr-defined]
    except ImportError:
        return _runtime_response(request, "runtime_defaults", payload)
    row = RuntimeDefaults.objects.order_by("-id").first()
    if row is not None:
        payload["defaults"] = {
            field.name: getattr(row, field.name)
            for field in row._meta.fields
            if field.name not in {"id", "created_at", "updated_at"}
            and isinstance(getattr(row, field.name), (str, int, float, bool, list, dict, type(None)))
        }
    return _runtime_response(request, "runtime_defaults", payload)


@extend_schema(tags=[_RUNTIME_TAG], summary="SiteSettings public-safe snapshot", description=_RUNTIME_DESCRIPTION)
@require_safe
@cache_control(public=True, max_age=15, s_maxage=900)
def site_settings_snapshot(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/runtime/site-settings — public-safe SiteSettings projection."""
    payload: dict[str, Any] = {"settings": {}}
    try:
        from apps.platform_runtime.helpers import get_effective_site_settings
    except ImportError:
        return _runtime_response(request, "site_settings_snapshot", payload)
    school = getattr(request, "school", None)
    row = get_effective_site_settings(request=request, school=school)
    if row is not None:
        # Public-safe projection: brand + locale + theme; never secrets.
        public_keys = ("brand_payload", "theme_personality", "cockpit_payload")
        for k in public_keys:
            v = getattr(row, k, None)
            if isinstance(v, dict):
                payload["settings"][k] = v
    return _runtime_response(request, "site_settings_snapshot", payload)


@extend_schema(tags=[_RUNTIME_TAG], summary="Resolved tenant feature flags", description=_RUNTIME_DESCRIPTION)
@require_safe
@cache_control(public=True, max_age=15, s_maxage=900)
def feature_flags_runtime(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/runtime/feature-flags — resolved flags for the current tenant."""
    payload: dict[str, Any] = {"flags": {}}
    school = getattr(request, "school", None)
    if school is None:
        return _runtime_response(request, "feature_flags", payload)
    flags = getattr(school, "features", None) or getattr(school, "features_json", None) or {}
    if isinstance(flags, dict):
        payload["flags"] = flags
    return _runtime_response(request, "feature_flags", payload)
