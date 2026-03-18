"""Integration readiness snapshot + LTI URLs for district hub (Phase J+)."""

from __future__ import annotations

from typing import Any

from django.db.models import Q
from apps.integrations_marketplace.models import ServiceIntegration
from apps.interop.oneroster.constants import ONEROSTER_DISTRICT_API_SERVICE_NAME


def _has_bearer(school) -> bool:
    for row in ServiceIntegration.objects.filter(school=school, is_active=True).filter(
        Q(service_name__icontains="oneroster")
        | Q(service_name__iexact=ONEROSTER_DISTRICT_API_SERVICE_NAME)
    ):
        c = row.config or {}
        if (c.get("bearer_token") or row.client_secret or "").strip():
            return True
    return False


def _lti_ready(school) -> tuple[str, str]:
    rows = ServiceIntegration.objects.filter(
        school=school, is_active=True, service_type=ServiceIntegration.ServiceType.LTI
    )
    for row in rows:
        cfg = row.config or {}
        if (cfg.get("deployment_id") or "").strip() and (
            (row.client_id or cfg.get("client_id") or "").strip()
        ):
            return "green", str(row.pk)
    return ("amber" if rows.exists() else "red"), ""


def _scim_hint(school) -> str:
    if ServiceIntegration.objects.filter(
        school=school, is_active=True, service_name__icontains="scim"
    ).exists():
        return "green"
    return "amber"


def _saml_oidc_hint(school) -> str:
    try:
        from apps.integrations_marketplace.models import Integration

        if (
            Integration.objects.filter(school=school, enabled=True)
            .filter(Q(provider__icontains="saml") | Q(provider__icontains="oidc"))
            .exists()
        ):
            return "green"
    except Exception:
        pass
    return "amber"


def integration_readiness_snapshot(school, request) -> dict[str, Any]:
    """Green / amber / red for hub dashboard."""
    oneroster = "green" if _has_bearer(school) else "red"
    lti_status, lti_tool_id = _lti_ready(school)
    base = request.build_absolute_uri("/").rstrip("/")
    slug = school.slug
    lti_wizard = {
        "platform_issuer": base,
        "jwks_url": request.build_absolute_uri("/lti/jwks.json"),
        "oidc_login_template": base + "/lti/launch/<tool_id>/",
        "school_slug": slug,
        "first_lti_tool_id": lti_tool_id,
    }
    return {
        "oneroster": oneroster,
        "lti": lti_status,
        "scim": _scim_hint(school),
        "sso": _saml_oidc_hint(school),
        "lti_wizard": lti_wizard,
        "sso_tips": {
            "saml_acs": "Configure IdP with SAML ACS URL from your SAML integration row.",
            "clock_skew": "If login fails intermittently, check IdP/server clock skew (NTP).",
            "cert_expiry": "Renew IdP signing cert before expiry; upload new metadata in Integrations.",
        },
    }
