"""Interoperability readiness endpoints for OneRoster and LTI 1.3."""

from django.http import JsonResponse

from apps.schools.models import School
from apps.siteconfig.models import ServiceIntegration


def _resolve_school(request):
    school = getattr(request, "school", None)
    if school:
        return school
    school_slug = (request.GET.get("school_slug") or "").strip()
    if not school_slug:
        return None
    return School.objects.filter(slug=school_slug, is_active=True).first()


def _integration_payload(*, service: str, school, service_type: str) -> tuple[dict, int]:
    payload = {
        "service": service,
        "service_type": service_type,
        "spec": "1EdTech",
        "status": "not_configured",
        "implemented": False,
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

    integration = (
        ServiceIntegration.objects.filter(
            school=school,
            service_type=service_type,
            is_active=True,
        )
        .order_by("-updated_at")
        .first()
    )

    payload.update({"school_id": school.pk, "school_slug": school.slug})
    if not integration:
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
            "integration_id": integration.pk,
            "integration_name": integration.service_name,
            "endpoint_url": integration.endpoint_url,
            "enabled_scopes": integration.enabled_scopes,
            "status": "configured",
            "implemented": bool(integration.endpoint_url),
        }
    )

    if not integration.endpoint_url:
        payload.update(
            {
                "status": "misconfigured",
                "detail": "Integration exists but endpoint_url is empty.",
            }
        )
        return payload, 503

    return payload, 200


def oneroster_stub(request):
    """OneRoster readiness endpoint."""
    school = _resolve_school(request)
    payload, status = _integration_payload(
        service="oneroster",
        school=school,
        service_type=ServiceIntegration.ServiceType.OAUTH,
    )
    payload["standard"] = "OneRoster 1.1"
    payload["resources"] = ["academicSessions", "classes", "students", "teachers", "enrollments"]
    return JsonResponse(payload, status=status)


def lti13_stub(request):
    """LTI 1.3 readiness endpoint."""
    school = _resolve_school(request)
    payload, status = _integration_payload(
        service="lti13",
        school=school,
        service_type=ServiceIntegration.ServiceType.LTI,
    )
    payload["standard"] = "LTI 1.3"
    payload["capabilities"] = ["oidc_login", "resource_link_launch", "ags", "nrps"]
    return JsonResponse(payload, status=status)
