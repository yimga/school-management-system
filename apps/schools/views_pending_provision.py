"""Public read-only provisioning progress for pending tenant subdomains (no login)."""

from __future__ import annotations

from django.http import HttpRequest, JsonResponse
from django.views.decorators.http import require_GET


def _resolve_pending_school(request: HttpRequest):
    school = getattr(request, "school", None)
    if school is not None:
        return school
    try:
        from apps.schools.pending_tenant_discovery import (
            lookup_school_by_slug_or_subdomain,
            pending_school_state,
        )
        from apps.schools.middleware import _extract_subdomain
        from django.conf import settings

        host = (request.get_host() or "").split(":", 1)[0]
        base_domain = getattr(settings, "MULTI_TENANT_BASE_DOMAIN", None) or "runmycampus.com"
        token = _extract_subdomain(host, base_domain)
        if not token:
            return None
        school = lookup_school_by_slug_or_subdomain(token)
        if school is None or not pending_school_state(school):
            return None
        request.school = school
        request.tenant_provisioning_pending = True
        return school
    except (ImportError, AttributeError, TypeError, ValueError):
        return None


def _public_progress_payload(school) -> dict:
    from apps.schools.provisioning_progress import resolve_provisioning_progress

    payload = resolve_provisioning_progress(school, include_dashboard_href=False)
    payload.pop("events", None)
    payload.pop("dashboard_href", None)
    return payload


@require_GET
def api_public_pending_provision_progress(request: HttpRequest) -> JsonResponse:
    """
    Anonymous poll for ``{slug}.runmycampus.com`` while the campus is still provisioning.

    Returns the same canonical contract as owner/tenant APIs minus PII and dashboard href.
    """
    school = _resolve_pending_school(request)
    if school is None:
        return JsonResponse({"ok": False, "error": "not_pending"}, status=404)
    return JsonResponse(_public_progress_payload(school))
