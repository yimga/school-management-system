"""Interoperability discovery/readiness endpoints for OneRoster and LTI 1.3."""

import json
from pathlib import Path

from django.conf import settings
from django.db.models import Q
from django.http import JsonResponse
from django.urls import reverse

from apps.api.rate_limit import throttle_ip_request
from apps.interop.district_readiness import parse_district_readiness_dict
from apps.schools.models import School
from apps.siteconfig.integration_registry import resolve_active_integration
from apps.integrations_marketplace.models import ServiceIntegration

INTEROP_DISCOVERY_RATE_LIMIT_WINDOW = 60 * 15
INTEROP_DISCOVERY_RATE_LIMIT_MAX = 120


def _interop_rate_limited(request, service: str):
    allowed, retry_after = throttle_ip_request(
        request,
        scope=f"interop_discovery:{service}",
        max_count=INTEROP_DISCOVERY_RATE_LIMIT_MAX,
        window_seconds=INTEROP_DISCOVERY_RATE_LIMIT_WINDOW,
    )
    if allowed:
        return None
    return JsonResponse(
        {
            "service": service,
            "status": "rate_limited",
            "implemented": True,
            "detail": "Too many discovery requests. Retry later.",
            "retry_after": retry_after,
            "message": "Wait before retrying (see retry_after seconds).",
        },
        status=429,
    )


def _resolve_school(request):
    school = getattr(request, "school", None)
    if school:
        return school
    school_slug = (request.GET.get("school_slug") or "").strip()
    if not school_slug:
        return None
    return School.objects.filter(slug=school_slug, is_active=True).first()


def _integration_payload(
    *, service: str, school, service_type: str, service_name_hint: str = ""
) -> tuple[dict, int]:
    payload = {
        "service": service,
        "service_type": service_type,
        "spec": "1EdTech",
        "status": "needs_configuration",
        "implemented": True,
    }

    if not school:
        payload.update(
            {
                "detail": "School context missing. Provide school_slug or call via tenant domain.",
                "next_steps": [
                    "Provide tenant school context",
                    "Configure ServiceIntegration for this service",
                ],
            }
        )
        return payload, 400

    integration_qs = ServiceIntegration.objects.filter(
        school=school,
        service_type=service_type,
        is_active=True,
    )
    if service_name_hint:
        integration_qs = integration_qs.filter(
            service_name__icontains=service_name_hint
        )
    integration = integration_qs.order_by("-updated_at").first()
    integration_record = None
    if integration:
        cfg = integration.config or {}
        integration_record = {
            "source": "service_integration",
            "integration_id": integration.pk,
            "integration_name": integration.service_name,
            "endpoint_url": integration.endpoint_url,
            "enabled_scopes": integration.enabled_scopes,
            "config": cfg,
            "has_auth_credentials": bool(
                (cfg or {}).get("bearer_token")
                or (cfg or {}).get("token")
                or (cfg or {}).get("api_key")
                or integration.client_secret
            ),
        }
    else:
        fallback = resolve_active_integration(school, service_name_hint or service)
        if fallback and fallback.service_type == service_type:
            cfg = fallback.config or {}
            integration_record = {
                "source": fallback.source,
                "integration_id": fallback.integration_id,
                "integration_name": fallback.service_name,
                "endpoint_url": fallback.endpoint_url,
                "enabled_scopes": fallback.enabled_scopes,
                "config": cfg,
                "has_auth_credentials": bool(
                    (cfg or {}).get("bearer_token")
                    or (cfg or {}).get("token")
                    or (cfg or {}).get("api_key")
                    or (cfg or {}).get("client_secret")
                ),
            }

    payload.update({"school_id": school.pk, "school_slug": school.slug})
    if not integration_record:
        payload.update(
            {
                "detail": "No active integration configuration for this service.",
                "next_steps": [
                    "Create ServiceIntegration entry",
                    "Set endpoint_url and required credentials in config",
                ],
            }
        )
        return payload, 503

    payload.update(
        {
            "integration_id": integration_record["integration_id"],
            "integration_name": integration_record["integration_name"],
            "integration_source": integration_record["source"],
            "endpoint_url": integration_record["endpoint_url"],
            "enabled_scopes": integration_record["enabled_scopes"],
            "has_auth_credentials": integration_record["has_auth_credentials"],
            "status": "configured",
            "implemented": True,
        }
    )

    return payload, 200


def oneroster_readiness(request):
    """OneRoster readiness/discovery endpoint."""
    rl = _interop_rate_limited(request, "oneroster")
    if rl:
        return rl
    school = _resolve_school(request)
    payload, status = _integration_payload(
        service="oneroster",
        school=school,
        service_type=ServiceIntegration.ServiceType.OAUTH,
        service_name_hint="oneroster",
    )
    payload["standard"] = "OneRoster 1.1"
    payload["resources"] = [
        "academicSessions",
        "classes",
        "students",
        "teachers",
        "enrollments",
        "orgs",
        "courses",
        "users",
    ]
    if school:
        payload["endpoints"] = {
            "manifest": request.build_absolute_uri(reverse("api:oneroster-manifest")),
            "academicSessions": request.build_absolute_uri(
                reverse("api:oneroster-academic-sessions")
            ),
            "classes": request.build_absolute_uri(reverse("api:oneroster-classes")),
            "students": request.build_absolute_uri(reverse("api:oneroster-students")),
            "teachers": request.build_absolute_uri(reverse("api:oneroster-teachers")),
            "enrollments": request.build_absolute_uri(
                reverse("api:oneroster-enrollments")
            ),
            "orgs": request.build_absolute_uri(reverse("api:oneroster-orgs")),
            "courses": request.build_absolute_uri(reverse("api:oneroster-courses")),
            "users": request.build_absolute_uri(reverse("api:oneroster-users")),
        }
    if status == 200:
        auth_ready = bool(payload.get("has_auth_credentials"))
        payload["status"] = "ready" if auth_ready else "needs_configuration"
        if not auth_ready:
            status = 503
            payload["detail"] = (
                "Integration exists but no OneRoster auth credential is configured."
            )
    return JsonResponse(payload, status=status)


def lti13_readiness(request):
    """LTI 1.3 readiness/discovery endpoint."""
    rl = _interop_rate_limited(request, "lti13")
    if rl:
        return rl
    school = _resolve_school(request)
    payload, status = _integration_payload(
        service="lti13",
        school=school,
        service_type=ServiceIntegration.ServiceType.LTI,
        service_name_hint="lti",
    )
    payload["standard"] = "LTI 1.3"
    payload["capabilities"] = ["oidc_login", "resource_link_launch", "ags", "nrps"]
    if status == 200:
        integration_id = payload.get("integration_id")
        integration = (
            # tenant-isolation-allow: scoped-via-surrounding-tenant-context-reviewed-2026-05-17
            ServiceIntegration.objects.filter(pk=integration_id).first()
            if integration_id
            else None
        )
        cfg = (integration.config if integration else {}) or {}
        auth_endpoint = (
            (
                cfg.get("authorization_endpoint") or integration.endpoint_url or ""
            ).strip()
            if integration
            else ""
        )
        client_id = (
            (integration.client_id or cfg.get("client_id") or "").strip()
            if integration
            else ""
        )
        deployment_id = (cfg.get("deployment_id") or "").strip() if integration else ""
        if not (auth_endpoint and client_id and deployment_id):
            payload["status"] = "needs_configuration"
            payload["detail"] = (
                "LTI integration missing one or more required fields: authorization_endpoint, client_id, deployment_id."
            )
            status = 503
        else:
            payload["status"] = "ready"
        if integration:
            payload["endpoints"] = {
                "oidc_login": request.build_absolute_uri(
                    reverse("lti_launch", args=[integration.pk])
                ),
                "oidc_callback": request.build_absolute_uri(
                    reverse("lti_launch_callback", args=[integration.pk])
                ),
                "jwks": request.build_absolute_uri(reverse("lti_jwks")),
                "ags_lineitems": request.build_absolute_uri(
                    reverse("lti_ags_lineitems", args=[integration.pk])
                ),
                "nrps_memberships": request.build_absolute_uri(
                    reverse("lti_nrps_memberships", args=[integration.pk])
                ),
                "deep_linking": request.build_absolute_uri(
                    reverse("lti_deep_linking", args=[integration.pk])
                ),
            }
    return JsonResponse(payload, status=status)


def oneroster_stub(request):
    """Backward-compatible alias."""
    return oneroster_readiness(request)


def lti13_stub(request):
    """Backward-compatible alias."""
    return lti13_readiness(request)


def edfi_readiness(request):
    """Ed-Fi adapter readiness (18.1, 31.2). Adapter and data API implemented."""
    rl = _interop_rate_limited(request, "edfi")
    if rl:
        return rl
    school = _resolve_school(request)
    payload = {
        "service": "edfi",
        "standard": "Ed-Fi API",
        "status": "implemented",
        "implemented": True,
        "detail": "Ed-Fi mapping and data API: students, studentSchoolAssociations, grades.",
        "endpoints": {
            "students": request.build_absolute_uri(
                reverse("api:interop-edfi-students")
            ),
            "studentSchoolAssociations": request.build_absolute_uri(
                reverse("api:interop-edfi-associations")
            ),
            "grades": request.build_absolute_uri(reverse("api:interop-edfi-grades")),
        },
    }
    if school:
        payload["school_id"] = school.pk
        payload["school_slug"] = school.slug
        integ = (
            ServiceIntegration.objects.filter(school=school, is_active=True)
            .filter(
                Q(service_name__icontains="edfi")
                | Q(config__has_key="district_readiness")
            )
            .order_by("-updated_at")
            .first()
        )
        if integ:
            dr = (integ.config or {}).get("district_readiness")
            if isinstance(dr, dict) and dr.get("district_identifier"):
                ss = dr.get("source_system")
                name_l = (integ.service_name or "").lower()
                if ss == "edfi" or "edfi" in name_l:
                    payload["district_readiness"] = {
                        "source_system": ss,
                        "district_identifier": str(dr.get("district_identifier")),
                        "name": dr.get("name"),
                    }
    return JsonResponse(payload, status=200)


def ceds_readiness(request):
    """CEDS for US reporting readiness (18.2). Mapping and data API implemented."""
    rl = _interop_rate_limited(request, "ceds")
    if rl:
        return rl
    school = _resolve_school(request)
    payload = {
        "service": "ceds",
        "standard": "CEDS (US)",
        "status": "implemented",
        "implemented": True,
        "detail": "CEDS mapping and data API: K12 students, enrollments, grades.",
        "endpoints": {
            "students": request.build_absolute_uri(
                reverse("api:interop-ceds-students")
            ),
            "enrollments": request.build_absolute_uri(
                reverse("api:interop-ceds-enrollments")
            ),
            "grades": request.build_absolute_uri(reverse("api:interop-ceds-grades")),
        },
    }
    if school:
        payload["school_id"] = school.pk
        payload["school_slug"] = school.slug
        integ = (
            ServiceIntegration.objects.filter(school=school, is_active=True)
            .filter(
                Q(service_name__icontains="ceds")
                | Q(config__has_key="district_readiness")
            )
            .order_by("-updated_at")
            .first()
        )
        if integ:
            dr = (integ.config or {}).get("district_readiness")
            if isinstance(dr, dict) and dr.get("district_identifier"):
                ss = dr.get("source_system")
                name_l = (integ.service_name or "").lower()
                if ss == "ceds" or "ceds" in name_l:
                    payload["district_readiness"] = {
                        "source_system": ss,
                        "district_identifier": str(dr.get("district_identifier")),
                        "name": dr.get("name"),
                    }
    return JsonResponse(payload, status=200)


def district_readiness_sample(request):
    """
    Fixture-driven HTTP stub: returns ``parse_district_readiness_dict`` output for repo samples.

    Query: ``fixture=edfi`` (default) or ``ceds``. Requires ``school_slug`` (or tenant host).
    """
    rl = _interop_rate_limited(request, "district_readiness")
    if rl:
        return rl
    school = _resolve_school(request)
    if not school:
        return JsonResponse(
            {
                "detail": "School context missing. Provide school_slug or call via tenant domain.",
                "implemented": True,
            },
            status=400,
        )
    fixture_key = (request.GET.get("fixture") or "edfi").strip().lower()
    rel = {
        "edfi": "fixtures/interop/edfi_district_readiness_sample.json",
        "ceds": "fixtures/interop/ceds_district_readiness_sample.json",
    }.get(fixture_key)
    if not rel:
        return JsonResponse(
            {"detail": "fixture must be 'edfi' or 'ceds'", "implemented": True},
            status=400,
        )
    path = Path(settings.BASE_DIR) / rel
    if not path.is_file():
        return JsonResponse(
            {"detail": "fixture file missing on server", "path": rel},
            status=500,
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    canonical = parse_district_readiness_dict(raw)
    return JsonResponse(canonical, status=200)


def interop_hub(request):
    """
    B6: Interoperability as first-class product surface. Single discovery endpoint
    listing all standards (Ed-Fi, CEDS, OneRoster, LTI 1.3, SCIM) with status and links.
    """
    base = request.build_absolute_uri("/api/").rstrip("/")
    payload = {
        "surface": "interoperability",
        "description": "RunMyCampus interoperability hub; all standards are first-class.",
        "standards": [
            {
                "id": "edfi",
                "name": "Ed-Fi API",
                "readiness_url": f"{base}/interop/edfi/",
                "implemented": True,
            },
            {
                "id": "ceds",
                "name": "CEDS (US)",
                "readiness_url": f"{base}/interop/ceds/",
                "implemented": True,
            },
            {
                "id": "oneroster",
                "name": "OneRoster 1.1",
                "readiness_url": f"{base}/interop/oneroster/",
                "implemented": True,
            },
            {
                "id": "lti13",
                "name": "LTI 1.3",
                "readiness_url": f"{base}/interop/lti13/",
                "implemented": True,
            },
            {
                "id": "scim",
                "name": "SCIM 2.0",
                "readiness_url": f"{base}/scim/v2/ServiceProviderConfig",
                "implemented": True,
            },
        ],
    }
    return JsonResponse(payload, status=200)
