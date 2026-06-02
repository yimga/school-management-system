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
  GET /structural-options    — country pack + matrix (public)
  POST /structural-options/initialize — tenant academic tree provision (auth)

The payloads are intentionally minimal — anything that needs auth or that
varies per user does NOT belong here.
"""

from __future__ import annotations

import json
from typing import Any

from django.http import HttpRequest, JsonResponse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_POST, require_safe

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
@cache_control(public=True, max_age=15, s_maxage=900)  # magic-number-allow: http-cache-max-age-seconds
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
        school_id = getattr(school, "pk", None) or getattr(school, "id", None)
        if school_id is not None:
            qs = qs.filter(school_id=school_id)
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
@cache_control(public=True, max_age=15, s_maxage=900)  # magic-number-allow: http-cache-max-age-seconds
def grading_matrix_runtime(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/runtime/grading-matrix — grading scale + cutoffs."""
    payload: dict[str, Any] = {
        "scale": [],
        "passing_threshold": None,
        "scale_code": "",
        "family": "",
        "boundary_map": [],
        "ranking_mode": "average",
        "preset_key": "",
    }
    school = getattr(request, "school", None)
    if school is None:
        return _runtime_response(request, "grading_matrix", payload)
    try:
        from apps.policies.resolver import get_effective_policy
        from apps.registries.grade_scale_resolver import resolve_grade_scale_for_tenant

        policy = get_effective_policy(school)
        scale = resolve_grade_scale_for_tenant(school)
        if scale:
            payload["scale_code"] = scale.code
            payload["family"] = scale.family or ""
            rd = scale.range_definition if isinstance(scale.range_definition, dict) else {}
            payload["passing_threshold"] = rd.get("pass_threshold") or rd.get("min")
            meta = scale.metadata if isinstance(scale.metadata, dict) else {}
            payload["boundary_map"] = meta.get("boundary_map") or []
            payload["ranking_mode"] = meta.get("ranking_mode") or "average"
        payload["preset_key"] = (policy.get("grading") or {}).get("preset_key") or ""
        payload["scale"] = policy.get("grading") or {}
    except (ImportError, AttributeError, TypeError, ValueError):
        settings_dict = getattr(school, "settings", None) or {}
        payload["scale"] = settings_dict.get("grading_scale") or []
        payload["passing_threshold"] = settings_dict.get("grading_passing_threshold")
    return _runtime_response(request, "grading_matrix", payload)


@extend_schema(tags=[_RUNTIME_TAG], summary="Structural onboarding options", description=_RUNTIME_DESCRIPTION)
@require_safe
@cache_control(public=True, max_age=15, s_maxage=900)  # magic-number-allow: http-cache-max-age-seconds
def structural_options_runtime(request: HttpRequest) -> JsonResponse:
    """GET /api/v1/runtime/structural-options?country=XX — country pack + matrix context."""
    country = (request.GET.get("country") or "").strip().upper()[:2]
    from apps.governance.academic_pack_bridge import resolve_academic_pack_context
    from apps.siteconfig.terminology_service import matrix_institution_vocabulary_with_structure

    ctx = resolve_academic_pack_context(country)
    school = getattr(request, "school", None)
    if not country and school is not None:
        country = str(getattr(school, "country_code", None) or "")[:2].upper()
    payload = {
        "country_code": country,
        "pack_source": ctx.get("pack_source"),
        "education_pack_tier": ctx.get("education_pack_tier_live"),
        "grading_preset_key": ctx.get("grading_preset_key"),
        "supports_multi_shift": ctx.get("supports_multi_shift"),
        "school_types": ctx.get("school_types") or [],
        "education_levels": ctx.get("education_levels") or [],
        "terminology": ctx.get("terminology") or {},
        "exam_boards": ctx.get("exam_boards") or [],
        "institution_vocabulary": matrix_institution_vocabulary_with_structure(
            country, school
        ),
    }
    return _runtime_response(request, "structural_options", payload)


def _require_tenant_member_for_runtime(request: HttpRequest):
    """Auth + tenant membership for mutating runtime endpoints."""
    school = getattr(request, "school", None)
    if school is None:
        return None, JsonResponse({"error": "Tenant context required"}, status=400)
    user = getattr(request, "user", None)
    if not user or not getattr(user, "is_authenticated", False):
        return None, JsonResponse({"error": "Authentication required"}, status=401)
    session_sid = ""
    if hasattr(request, "session"):
        session_sid = (request.session.get("school_id") or "").strip()
    try:
        from apps.schools.tenant_switch_security import user_may_access_school_api

        if not user_may_access_school_api(
            user, school, session_school_id=session_sid or None
        ):
            return None, JsonResponse({"error": "Forbidden"}, status=403)
    except ImportError:
        return None, JsonResponse({"error": "Forbidden"}, status=403)
    return school, None


@extend_schema(
    tags=[_RUNTIME_TAG],
    summary="Provision academic structure for current tenant",
    description="Idempotent cycle/classroom nodes from pack + school_type selection.",
)
@require_POST
def structural_options_initialize_runtime(request: HttpRequest) -> JsonResponse:
    """POST /api/v1/runtime/structural-options/initialize — provision academic tree."""
    school, err = _require_tenant_member_for_runtime(request)
    if err is not None:
        return err

    body: dict[str, Any] = {}
    if request.body:
        try:
            parsed = json.loads(request.body.decode("utf-8"))
            if isinstance(parsed, dict):
                body = parsed
        except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError):
            return JsonResponse({"error": "Invalid JSON body"}, status=400)

    raw_types = body.get("school_type_codes") or body.get("school_types") or []
    school_type_codes: list[str] = []
    if isinstance(raw_types, list):
        school_type_codes = [str(c).strip() for c in raw_types if str(c).strip()]
    if not school_type_codes:
        settings_dict = getattr(school, "settings", None) or {}
        if isinstance(settings_dict, dict):
            raw = str(
                settings_dict.get("school_type")
                or settings_dict.get("school_type_raw")
                or ""
            ).strip()
            school_type_codes = [
                t.strip() for t in raw.replace(",", "|").split("|") if t.strip()
            ]

    from apps.academics.structure_provisioning import provision_academic_structure_for_school
    from apps.policies.grading_nuance_templates import sync_grading_nuance_from_policy

    structure_payload = provision_academic_structure_for_school(
        school,
        school_type_codes=school_type_codes or None,
    )
    nuance_payload = sync_grading_nuance_from_policy(school)
    payload = {
        "status": "ok",
        "structure": structure_payload,
        "nuance_sync": nuance_payload,
    }
    response = JsonResponse(payload, json_dumps_params={"separators": (",", ":")})
    stamp_response(
        response,
        tenant=_resolve_tenant_slug(request),
        view="structural_options_initialize",
        viewport=_resolve_viewport(request),
    )
    return response


@extend_schema(tags=[_RUNTIME_TAG], summary="RuntimeDefaults projection", description=_RUNTIME_DESCRIPTION)
@require_safe
@cache_control(public=True, max_age=15, s_maxage=900)  # magic-number-allow: http-cache-max-age-seconds
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
@cache_control(public=True, max_age=15, s_maxage=900)  # magic-number-allow: http-cache-max-age-seconds
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
@cache_control(public=True, max_age=15, s_maxage=900)  # magic-number-allow: http-cache-max-age-seconds
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
